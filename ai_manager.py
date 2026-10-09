"""
config.py
Constants, logging, fail-fast env checks, and the shared HTTP session.
Import this first; every other module depends on it.
"""

import os
import logging
import requests

# --------------------------------------------------------------------------
# Logging (set up first so every other module can log safely)
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
