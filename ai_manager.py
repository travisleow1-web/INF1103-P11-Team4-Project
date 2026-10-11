import os
import json
import logging
import requests
import time
import random
from typing import Optional, Dict, Any, List, Tuple, Callable

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
CACHE_FILE = "ai_cache.json"
MAX_RETRIES = 3
HTTP_TIMEOUT = 20
MAX_PLACES_LIMIT = 4
GDELT_MAX_RECORDS = 8
GDELT_TIMESPAN = "3d"
TIMEZONE = "Asia/Singapore"
FORECAST_DAYS = 16  # Open-Meteo's maximum
WEATHER_VARIABLES = ("wind_speed_10m", "wind_gusts_10m", "pressure_msl", "visibility")

# Exactly the columns io_manager.input_method() returns, in the same order.
SHIPMENT_FIELDS = (
    "shipment_id", "origin_port", "origin_lat", "origin_lon",
    "destination_port", "destination_lat", "destination_lon",
    "departure_time", "arrival_time",
)

# --------------------------------------------------------------------------
# Gemini settings
# --------------------------------------------------------------------------
# Double-check this model ID against what your account supports.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

ALLOWED_RISK_TYPES = [
    "weather", "severe_crosswinds", "port_congestion", "labor_shortage",
    "piracy_threat", "severe_civil_unrest", "geopolitical",
    "infrastructure_disruption",
]
ALLOWED_SEVERITY = ["Low", "Medium", "High"]
ALLOWED_IMPACT = ["Delay", "Cost Increase", "Cargo Damage", "Cargo Destruction", "None"]

SYSTEM_PROMPT = """You are a logistics risk analyst for shipments passing through or destined for Singapore.
Your role is exclusively to analyse, structure, and quantify risk factors from provided feeds.
You NEVER decide operational actions (such as proceed, delay, reroute, or insure): downstream business rules execute those.

Rules:
- Identify ALL distinct risk factors present across the data. Do NOT omit moderate or low risks.
- Use ONLY the shipment data and external data provided. Do not invent facts.
- If data is missing, old, or contradictory, lower confidence_score and set conflicting_sources to true."""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "risk_factors": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "type": {"type": "STRING", "enum": ALLOWED_RISK_TYPES},
                    "severity": {"type": "STRING", "enum": ALLOWED_SEVERITY},
                    "detail": {"type": "STRING"},
                },
                "required": ["type", "severity", "detail"],
            },
        },
        "primary_risk_factor": {"type": "STRING", "enum": ALLOWED_RISK_TYPES},
        "affected_location": {"type": "STRING"},
        "expected_impact": {"type": "STRING", "enum": ALLOWED_IMPACT},
        "confidence_score": {"type": "NUMBER"},
        "sources": {"type": "ARRAY", "items": {"type": "STRING"}},
        "conflicting_sources": {"type": "BOOLEAN"},
        "extreme_event": {"type": "STRING"},
        "insights": {"type": "ARRAY", "items": {"type": "STRING"}},
        "alternative_route": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING"},
                "distance_km": {"type": "NUMBER"},
            },
        },
    },
    "required": [
        "risk_factors", "primary_risk_factor", "affected_location",
        "expected_impact", "confidence_score", "sources",
        "conflicting_sources", "extreme_event", "insights",
    ],
}
# --------------------------------------------------------------------------
# Connection pooling
# --------------------------------------------------------------------------
http_session = requests.Session()

# Add FALLBACK_AI_RESPONSE as the safe default when enrichment fails
FALLBACK_AI_RESPONSE: Dict[str, Any] = {
    "risk_factors": [],  
    "primary_risk_factor": "infrastructure_disruption",
    "affected_location": "Unknown",
    "expected_impact": "None",
    "confidence_score": 0.0,
    "sources": ["System Fallback - External Feeds or AI API Failure"],
    "conflicting_sources": True,
    "extreme_event": "None",
    "insights": ["AI enrichment failed to complete. System defaulted to safety status."],
    "alternative_route": None,
}


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
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


def get_api_key() -> Optional[str]:
    """Return the Gemini API key, or None (and log it) if it isn't set.

    Read at call time rather than import time so a missing key never crashes
    the app; callers fall back to FALLBACK_AI_RESPONSE instead.
    """
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
    #Automatically retries an API request if it temporarily fails,
    #Waiting slightly longer after each attempt to give the server time to recover.
    """Retry a function if it raises, waiting longer after each attempt."""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    log.warning(
                        "%s attempt %d/%d failed: %s",
                        func.__name__, attempt, max_retries, exc,
                    )
                    if attempt == max_retries:
                        raise
                    time.sleep(delay * (1 + (random.random() if jitter else 0)))
                    delay *= backoff_factor
        return wrapper
    return decorator

# Add extract_shipment() to select the shipment fields used by the AI and cache key
def extract_shipment(record: Dict[str, Any]) -> Dict[str, Any]:
    """Pick only the shipment fields the AI (and the cache key) care about."""
    return {k: record[k] for k in SHIPMENT_FIELDS if k in record}

# Add build_prompt() to combine shipment and external data into the model prompt
def build_prompt(shipment: Dict[str, Any], external: Dict[str, Any]) -> str:
    return (
        "SHIPMENT:\n" + json.dumps(shipment, default=str)
        + "\n\nEXTERNAL DATA:\n" + json.dumps(external, default=str)
    )

@retry_with_smart_delay(max_retries=MAX_RETRIES)
def call_gemini(prompt: str) -> Dict[str, Any]:
    api_key = get_api_key()
    if api_key is None:
        raise RuntimeError("GEMINI_API_KEY is not set")

    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    r = http_session.post(
        GEMINI_URL,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=HTTP_TIMEOUT * 2,
    )
    r.raise_for_status()

    # responseSchema constrains Gemini to valid JSON matching our shape.
    raw_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(raw_text)

def _geocode(place: str) -> Optional[Tuple[float, float]]:
    r = http_session.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": place, "count": 1},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        return None
    return results[0]["latitude"], results[0]["longitude"]


def fetch_weather(lat: float, lon: float) -> Dict[str, Any]:
    """Return the hourly Open-Meteo forecast (WEATHER_VARIABLES) for a coordinate pair.

    Covers FORECAST_DAYS days; the dict has a "time" list plus one list per
    variable. Raises on network/HTTP errors; callers decide how to handle failure.
    """
    r = http_session.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "timezone": "auto",
            "forecast_days": FORECAST_DAYS,
            "hourly": ",".join(WEATHER_VARIABLES),
            "cell_selection": "sea",
        },
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return r.json().get("hourly", {})


def get_shipment_weather(shipment: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch the forecast at a shipment's origin and destination coordinates.

    A failed fetch is logged and stored as None, so one bad feed never stops
    the run.
    """
    weather = {}
    for end in ("origin", "destination"):
        try:
            weather[end] = fetch_weather(shipment[f"{end}_lat"], shipment[f"{end}_lon"])
        except Exception as exc:
            log.warning("weather feed failed for %s %s: %s", shipment.get("shipment_id"), end, exc)
            weather[end] = None
    return weather


def _weather(place: str) -> Dict[str, Any]:
    coords = _geocode(place)
    if coords is None:
        return {"place": place, "error": "location not found"}
    lat, lon = coords
    r = http_session.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "timezone": "auto",
            "forecast_days": 7,
            "daily": "precipitation_sum,wind_gusts_10m_max,weather_code",
            "cell_selection": "sea",
        },
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    return {"place": place, "source": "open-meteo.com", "daily": r.json().get("daily", {})}


def _news(places: List[str]) -> List[Dict[str, Any]]:
    place_q = " OR ".join(f'"{p}"' for p in places if p)
    topic_q = 'piracy OR "armed robbery" OR "port congestion" OR strike OR protest OR unrest'
    r = http_session.get(
        "https://api.gdeltproject.org/api/v2/doc/doc",
        params={
            "query": f"({place_q}) ({topic_q})",
            "mode": "ArtList",
            "maxrecords": GDELT_MAX_RECORDS,
            "format": "json",
            "timespan": GDELT_TIMESPAN,
        },
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    articles = r.json().get("articles", [])
    return [{"title": a.get("title"), "url": a.get("url"), "seen": a.get("seendate")} for a in articles]


def fetch_external_data(record: Dict[str, Any]) -> Dict[str, Any]:
    places = [record.get("origin"), record.get("destination")] + list(record.get("waypoints", []))
    places = [p for p in places if p]  # drop empty values

    data: Dict[str, Any] = {"weather": [], "news": [], "errors": []}

    for place in places[:MAX_PLACES_LIMIT]:
        try:
            data["weather"].append(_weather(place))
        except Exception as exc:
            log.warning("weather feed failed for %s: %s", place, exc)
            data["errors"].append(f"weather:{place}")

    try:
        data["news"] = _news(places[:MAX_PLACES_LIMIT])
    except Exception as exc:
        log.warning("news feed failed: %s", exc)
        data["errors"].append("news")

    return data
