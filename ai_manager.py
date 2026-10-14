import os
import json
import time
import random
import logging
import requests
import validator
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, Callable

from config import (
    MAX_RETRIES, HTTP_TIMEOUT, SHIPMENT_FIELDS, 
    SYSTEM_PROMPT, RESPONSE_SCHEMA, FALLBACK_AI_RESPONSE, GEMINI_URL
)
from cache import get_cache_key, cache_get, cache_set
from feeds import get_shipment_weather, fetch_news


# Logging Setup
log = logging.getLogger("ai_manager")
log.setLevel(logging.DEBUG)

if not log.handlers:
    file_handler = logging.FileHandler("app.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    log.addHandler(file_handler)

http_session = requests.Session()

# Helper Functions & Decorators
def get_api_key() -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY") or None
    if key is None:
        log.error("GEMINI_API_KEY is not set; AI calls will use the fallback response.")
    return key

def retry_with_smart_delay(
    max_retries: int = MAX_RETRIES,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
):
    #Decorator implementing exponential backoff and random jitter for transient errors. 
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs) 
                # If an exception occurs, log the attempt and wait before retrying, with increasing delay and optional jitter.
                except Exception as exc:
                    log.warning("%s attempt %d/%d failed: %s", func.__name__, attempt, max_retries, exc)
                    if attempt == max_retries:
                        raise
                    # Wait progressively longer, adding jitter to prevent thundering herd
                    time.sleep(delay * (1 + (random.random() if jitter else 0)))
                    delay *= backoff_factor
        return wrapper
    return decorator

def extract_shipment(record: Dict[str, Any]) -> Dict[str, Any]:
   # Isolate core shipment attributes used for cache key generation.
    return {k: record[k] for k in SHIPMENT_FIELDS if k in record}

def fill_coordinates(shipment: Dict[str, Any]) -> Dict[str, Any]:
    #Ensure port codes are uppercase and look up missing lat/lon coordinates from reference data.
    shipment = dict(shipment)
    for end in ("origin", "destination"):
        code = str(shipment.get(f"{end}_port", "")).strip().upper()
        shipment[f"{end}_port"] = code
        lat, lon = shipment.get(f"{end}_lat"), shipment.get(f"{end}_lon")
        missing = any(v is None or v == "" or (isinstance(v, float) and v != v) for v in (lat, lon))
        if missing and code in validator.PORTS_BY_CODE:
            shipment[f"{end}_lat"], shipment[f"{end}_lon"] = validator.port_coordinates(code)
    return shipment

def build_prompt(shipment: Dict[str, Any], external: Dict[str, Any]) -> str:
    # Format shipment parameters and live external data into a unified prompt string.
    return (
        "SHIPMENT:\n" + json.dumps(shipment, default=str)
        + "\n\nEXTERNAL DATA:\n" + json.dumps(external, default=str)
    )

@retry_with_smart_delay(max_retries=MAX_RETRIES)
def call_gemini(prompt: str) -> Dict[str, Any]:
    # Call the Gemini API with the given prompt, returning the parsed JSON response.
    api_key = get_api_key()
    if api_key is None:
        raise RuntimeError("GEMINI_API_KEY is not set")
    # Build the request body according to Gemini's expected schema, including system instructions and generation configuration.
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "seed": 0,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    # Send the request to Gemini and parse the response, raising an exception on failure.
    r = http_session.post(
        GEMINI_URL,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=HTTP_TIMEOUT * 2,
    )
    # Raise an exception for any HTTP error responses, then extract and parse the JSON content from the first candidate in the response.
    r.raise_for_status()
    raw_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(raw_text)

# Core Pipeline & Main Entry Points
def enrich_record(record: Dict[Any, Any]) -> Dict[str, Any]:
    # Enrich a single shipment record with external data and an AI assessment, using caching to avoid redundant API calls.
    shipment = fill_coordinates(record)
    key = get_cache_key(extract_shipment(shipment))
    # Check the cache for a previous assessment of this shipment; if found, return it with the cached timestamp.
    cached = cache_get(key)
    if cached:
        log.info("cache hit for %s", shipment.get("shipment_id"))
        return {**shipment, **cached["result"], "external_data_fetched_at": cached["fetched_at"]}
    # If not cached, fetch external data (weather and news) and call the AI model to get a new assessment, then cache the result.
    external = {"weather": get_shipment_weather(shipment), "news": fetch_news(shipment)}
    fetched_at = datetime.now().isoformat(timespec="seconds")
    # Call the Gemini API with the constructed prompt and handle any exceptions, falling back to a default response if necessary.
    try:
        result = call_gemini(build_prompt(shipment, external))
        if not all(k in result for k in RESPONSE_SCHEMA["required"]):
            raise ValueError("Gemini response missing required fields")
        cache_set(key, {"result": result, "fetched_at": fetched_at})
        # Log the successful assessment and return the enriched record.
    except Exception as exc:
        log.error("AI assessment failed for %s: %s", shipment.get("shipment_id"), exc)
        result = dict(FALLBACK_AI_RESPONSE)
        # Log the fallback response and return it with the current timestamp.
    return {**shipment, **result, "external_data_fetched_at": fetched_at}

def assess_shipments(shipments: pd.DataFrame) -> pd.DataFrame:
    # Assess a batch of shipments, enriching each record with external data and AI-generated insights, while handling errors gracefully.
    rows = []
    for record in shipments.to_dict("records"):
        try:
            rows.append(enrich_record(record))
        except Exception as exc:
            # Log the error and append a fallback response for this shipment, ensuring that the assessment process continues for other records.
            log.error("could not assess %s: %s", record.get("shipment_id"), exc)
            rows.append({**record, **FALLBACK_AI_RESPONSE,
                         "external_data_fetched_at": datetime.now().isoformat(timespec="seconds")})
    return pd.DataFrame(rows)