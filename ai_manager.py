import os
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

SHIPMENT_FIELDS = (
    "origin", "destination", "waypoints", "transport_mode", "transport_type",
    "goods", "departure_date", "expected_arrival", "baseline_distance_km",
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
# Fail-fast validation
# --------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("CRITICAL ERROR: 'GEMINI_API_KEY' is not set. The application cannot start.")

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
