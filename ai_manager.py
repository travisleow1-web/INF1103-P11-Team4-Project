import os
import json
import time
import random
import hashlib
import logging
import requests
import validator
import pandas as pd
from zoneinfo import ZoneInfo
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
CACHE_FILE = "ai_cache.json"
MAX_RETRIES = 3
HTTP_TIMEOUT = 20
TIMEZONE = "Asia/Singapore"

# Bump this whenever RESPONSE_SCHEMA changes, so old cached answers in the
# previous format are never reused.
SCHEMA_VERSION = 2

# Exactly the columns io_manager.input_method() returns, in the same order.
SHIPMENT_FIELDS = (
    "shipment_id", "origin_port", "origin_lat", "origin_lon",
    "destination_port", "destination_lat", "destination_lon",
    "departure_time", "arrival_time",
)

# --------------------------------------------------------------------------
# Shared field definitions
# --------------------------------------------------------------------------
# Every value the AI returns comes from one of these lists, so the Logic
# Manager can match on exact values instead of reading sentences.
# logic_manager.py imports these lists, so both managers always use the
# same field inputs. Change them here only.
with open("waypoints_reference.json", encoding="utf-8") as f:
    WAYPOINT_NAMES = [w["name"] for w in json.load(f)["waypoints"]]

ALLOWED_RISK_TYPES = [
    "weather", "severe_crosswinds", "port_congestion", "labor_shortage",
    "piracy_threat", "severe_civil_unrest", "geopolitical",
    "infrastructure_disruption",
]
ALLOWED_SEVERITY = ["Low", "Medium", "High"]
ALLOWED_IMPACT = ["Delay", "Cost Increase", "Cargo Damage", "Cargo Destruction", "None"]

# Where a risk applies: a port code from ports_reference_4.json, a waypoint
# name from waypoints_reference.json, the whole route, or unknown.
ALLOWED_LOCATIONS = sorted(validator.PORTS_BY_CODE) + WAYPOINT_NAMES + ["Route", "Unknown"]

ALLOWED_EXTREME_EVENTS = [
    "none", "typhoon", "hurricane", "cyclone", "earthquake", "tsunami",
    "port_closure", "vessel_collision", "armed_attack", "other",
]

ALLOWED_SOURCES = ["open_meteo_weather", "open_meteo_marine", "gdelt_news", "shipment_data"]

# Machine-readable insight codes. The Logic Manager's business rules act on
# these codes, so add a matching rule there if you add a code here.
INSIGHT_CODES = [
    "POTENTIAL_DELAY",      # conditions likely to delay departure or arrival
    "MULTIPLE_RISKS",       # several risks occurring at the same time
    "EXTREME_EVENT",        # sudden severe event (typhoon, port closure, attack)
    "CONFLICTING_DATA",     # sources disagree with each other
    "OUTDATED_DATA",        # a feed is old or stale
    "MISSING_DATA",         # a feed is empty or failed
    "NEEDS_HUMAN_REVIEW",   # anything else a person should look at
]
INSIGHT_RISK_TYPES = ALLOWED_RISK_TYPES + ["none"]

# --------------------------------------------------------------------------
# Gemini settings
# --------------------------------------------------------------------------
# Double-check this model ID against what your account supports.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)

SYSTEM_PROMPT = """You are a logistics risk analyst for shipments passing through or destined for Singapore.
Your role is exclusively to analyse, structure, and quantify risk factors from provided feeds.
You NEVER decide operational actions (such as proceed, delay, reroute, or insure): downstream business rules execute those.

Rules:
- Identify ALL distinct risk factors present across the data. Do NOT omit moderate or low risks.
- Use ONLY the shipment data and external data provided. Do not invent facts.
- If data is missing, old, or contradictory, lower confidence_score and set conflicting_sources to true.
- confidence_score is a number from 0.0 to 1.0.
- Output is read by code, not people. NEVER write sentences or prose in any field.
- risk_factors[].detail is a single key=value token for the measurement behind the risk,
  e.g. wind_gust_kmh=72, wave_height_m=4.1, visibility_m=800, news_articles=3.
- Locations: use the port code (e.g. CNSHA) for ports, the waypoint name for straits and seas,
  "Route" for the whole journey, "Unknown" if it cannot be placed.
- alternative_route: only if a named waypoint offers a safer path; distance_km is the full
  estimated sea distance of that alternative route. Omit it otherwise.
- insights: one object per finding. risk_type is "none" for data-quality findings.
  estimated_delay_days is your best estimate of added delay in whole days (0 if none or unknown).
  Use MULTIPLE_RISKS when two or more risk factors are Medium or higher."""

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
                    "location": {"type": "STRING", "enum": ALLOWED_LOCATIONS},
                    "source": {"type": "STRING", "enum": ALLOWED_SOURCES},
                    "detail": {"type": "STRING"},
                },
                "required": ["type", "severity", "location", "source", "detail"],
            },
        },
        "primary_risk_factor": {"type": "STRING", "enum": ALLOWED_RISK_TYPES},
        "affected_location": {"type": "STRING", "enum": ALLOWED_LOCATIONS},
        "expected_impact": {"type": "STRING", "enum": ALLOWED_IMPACT},
        "confidence_score": {"type": "NUMBER"},
        "sources": {"type": "ARRAY", "items": {"type": "STRING", "enum": ALLOWED_SOURCES}},
        "conflicting_sources": {"type": "BOOLEAN"},
        "extreme_event": {"type": "STRING", "enum": ALLOWED_EXTREME_EVENTS},
        "insights": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "code": {"type": "STRING", "enum": INSIGHT_CODES},
                    "risk_type": {"type": "STRING", "enum": INSIGHT_RISK_TYPES},
                    "severity": {"type": "STRING", "enum": ALLOWED_SEVERITY},
                    "location": {"type": "STRING", "enum": ALLOWED_LOCATIONS},
                    "estimated_delay_days": {"type": "INTEGER"},
                },
                "required": ["code", "risk_type", "severity", "location", "estimated_delay_days"],
            },
        },
        "alternative_route": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "enum": WAYPOINT_NAMES},
                "distance_km": {"type": "NUMBER"},
            },
            "required": ["name", "distance_km"],
        },
    },
    "required": [
        "risk_factors", "primary_risk_factor", "affected_location",
        "expected_impact", "confidence_score", "sources",
        "conflicting_sources", "extreme_event", "insights",
    ],
}

# Safe default when enrichment fails: low confidence + MISSING_DATA makes the
# Logic Manager send the shipment to human review.
FALLBACK_AI_RESPONSE: Dict[str, Any] = {
    "risk_factors": [],
    "primary_risk_factor": "infrastructure_disruption",
    "affected_location": "Unknown",
    "expected_impact": "None",
    "confidence_score": 0.0,
    "sources": [],
    "conflicting_sources": True,
    "extreme_event": "none",
    "insights": [{
        "code": "MISSING_DATA", "risk_type": "none", "severity": "High",
        "location": "Route", "estimated_delay_days": 0,
    }],
    "alternative_route": None,
}

# --------------------------------------------------------------------------
# Connection pooling
# --------------------------------------------------------------------------
http_session = requests.Session()

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

# --------------------------------------------------------------------------
# Response cache (one Gemini call per shipment per day)
# --------------------------------------------------------------------------
_cache: Optional[Dict[str, Any]] = None  # loaded once, kept in memory


def _load_cache() -> Dict[str, Any]:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Failed to load AI response cache from %s: %s", CACHE_FILE, exc)
        return {}


def _save_cache(cache_data: Dict[str, Any]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, default=str)
    except Exception as exc:
        log.warning("Failed to save AI response to %s: %s", CACHE_FILE, exc)


def get_cache_key(shipment: Dict[str, Any]) -> str:
    """Deterministic SHA-256 of the shipment fields, today's date and the schema version.

    shipment_id is left out so the same route and dates hit the cache even
    when the IDs are renumbered between runs.
    """
    today = datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()
    fields = {k: v for k, v in shipment.items() if k != "shipment_id"}
    payload = json.dumps(fields, sort_keys=True, default=str) + f"|{today}|v{SCHEMA_VERSION}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_get(key: str) -> Optional[Dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _load_cache()
    return _cache.get(key)


def cache_set(key: str, value: Dict[str, Any]) -> None:
    global _cache
    if _cache is None:
        _cache = _load_cache()
    _cache[key] = value
    _save_cache(_cache)


# --------------------------------------------------------------------------
# Gemini call
# --------------------------------------------------------------------------
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
    """Retry a function if it raises, waiting longer after each attempt
    to give the server time to recover."""
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


def extract_shipment(record: Dict[str, Any]) -> Dict[str, Any]:
    """Pick only the shipment fields the AI (and the cache key) care about."""
    return {k: record[k] for k in SHIPMENT_FIELDS if k in record}


def fill_coordinates(shipment: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with upper-case port codes and lat/lon looked up from the port reference.

    Manual entry already supplies the coordinates; CSV rows may only have port
    codes, so any missing or blank lat/lon is filled in here. Unknown port
    codes are left as they are (the weather feed for them is logged as failed).
    """
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
    """Combine shipment and external data into the model prompt."""
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
            "temperature": 0,
            "seed": 0,
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


# --------------------------------------------------------------------------
# External feeds
# --------------------------------------------------------------------------
def fetch_weather(lat: float, lon: float) -> Dict[str, Any]:
    """Return 16 days (Open-Meteo's maximum) of hourly weather and wave data.

    Raises on network/HTTP errors; callers decide how to handle failure.
    """
    return {
        **http_session.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "timezone": "auto",
                "forecast_days": 16,
                "hourly": "wind_speed_10m,wind_gusts_10m,pressure_msl,visibility",
                "cell_selection": "sea",
            },
            timeout=HTTP_TIMEOUT,
        ).json()["hourly"],
        **http_session.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params={
                "latitude": lat,
                "longitude": lon,
                "timezone": "auto",
                "forecast_days": 16,
                "hourly": "wave_height,swell_wave_height,wave_period",
            },
            timeout=HTTP_TIMEOUT,
        ).json()["hourly"],
    }


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


def fetch_news(shipment: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Return recent English GDELT headlines about risks at a shipment's ports.

    Returns [] when GDELT has no matching articles and None if the feed fails
    (logged), so one bad feed never stops the run. GDELT allows one request
    every 5 seconds, hence the sleep.
    """
    time.sleep(5)
    try:
        return [
            {"title": a["title"], "seen": a["seendate"]}
            for a in http_session.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": (
                        f'("{validator.PORTS_BY_CODE[shipment["origin_port"]]["name"]}"'
                        f' OR "{validator.PORTS_BY_CODE[shipment["destination_port"]]["name"]}")'
                        ' (piracy OR "armed robbery" OR "port congestion" OR strike OR protest OR unrest)'
                        ' sourcelang:english'
                    ),
                    "mode": "ArtList",
                    "maxrecords": 8,
                    "format": "json",
                    "timespan": "3d",
                },
                timeout=HTTP_TIMEOUT,
            ).json().get("articles", [])
        ]
    except Exception as exc:
        log.warning("news feed failed for %s: %s", shipment.get("shipment_id"), exc)
        return None

def enrich_record(record: Dict[Any, Any]) -> Dict[str, Any]:
    """Enrich ONE shipment: cache check, else feeds + Gemini. Always returns a dict.

    Failures are never cached; they get FALLBACK_AI_RESPONSE instead.
    """
    shipment = fill_coordinates(record)
    key = get_cache_key(extract_shipment(shipment))

    cached = cache_get(key)
    if cached:
        log.info("cache hit for %s", shipment.get("shipment_id"))
        return {**shipment, **cached["result"],
                "external_data_fetched_at": cached["fetched_at"]}

    external = {"weather": get_shipment_weather(shipment), "news": fetch_news(shipment)}
    fetched_at = datetime.now().isoformat(timespec="seconds")
    try:
        result = call_gemini(build_prompt(shipment, external))
        if not all(k in result for k in RESPONSE_SCHEMA["required"]):
            raise ValueError("Gemini response missing required fields")
        cache_set(key, {"result": result, "fetched_at": fetched_at})
    except Exception as exc:
        log.error("AI assessment failed for %s: %s", shipment.get("shipment_id"), exc)
        result = dict(FALLBACK_AI_RESPONSE)
    return {**shipment, **result, "external_data_fetched_at": fetched_at}
# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
def assess_shipments(shipments: pd.DataFrame) -> pd.DataFrame:
    """Return one row per shipment: the original columns plus Gemini's response fields.

    Each row also gets external_data_fetched_at (ISO time the feeds were read)
    for the Logic Manager's outdated-data check. A shipment already assessed
    today is served from ai_cache.json instead of calling the APIs again.
    If the API call fails or the response is missing required fields, the row
    gets FALLBACK_AI_RESPONSE (failures are never cached).

    Nothing is saved to shipments.json here: main.py saves each row through
    data_manager.add_record once the Logic Manager has made its decision.
    """
    rows = [enrich_record(s) for s in shipments.to_dict("records")]
    return pd.DataFrame(rows)