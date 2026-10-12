import json
import logging
import os
import random
import time
from datetime import datetime
import pandas as pd
import requests
import validator

MAX_RETRIES, HTTP_TIMEOUT = 3, 20

# ---------------- Shared field definitions (imported by logic_manager) ----------------
with open("waypoints_reference.json", encoding="utf-8") as f:
    WAYPOINT_NAMES = [w["name"] for w in json.load(f)["waypoints"]]
ALLOWED_RISK_TYPES = ["weather", "severe_crosswinds", "port_congestion", "labor_shortage", "piracy_threat",
                      "severe_civil_unrest", "geopolitical", "infrastructure_disruption"]
ALLOWED_SEVERITY = ["Low", "Medium", "High"]
ALLOWED_IMPACT = ["Delay", "Cost Increase", "Cargo Damage", "Cargo Destruction", "None"]
ALLOWED_LOCATIONS = sorted(validator.PORTS_BY_CODE) + WAYPOINT_NAMES + ["Route", "Unknown"]
ALLOWED_SOURCES = ["open_meteo_weather", "open_meteo_marine", "gdelt_news", "shipment_data"]
INSIGHT_CODES = ["POTENTIAL_DELAY", "MULTIPLE_RISKS", "CONFLICTING_DATA", "OUTDATED_DATA", "MISSING_DATA",
                 "NEEDS_HUMAN_REVIEW"]
INSIGHT_RISK_TYPES = ALLOWED_RISK_TYPES + ["none"]

# ---------------- Gemini settings ----------------
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")  # check your account supports this model
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_PROMPT = """You are a logistics risk analyst for shipments passing through or destined for Singapore.
You only analyse and structure risk from the data provided. You NEVER decide operational actions
(proceed, delay, insure): downstream business rules do that.
Rules:
- Identify ALL distinct risk factors, including moderate and low ones. Use ONLY the data provided.
- If data is missing, old or contradictory, lower confidence_score (0.0 to 1.0) and set conflicting_sources to true.
- Output is read by code, not people: NEVER write sentences in any field.
- risk_factors[].detail is one key=value token for the measurement behind the risk, e.g. wind_gust_kmh=72.
- Locations: the port code (e.g. CNSHA), a waypoint name for straits and seas, "Route" or "Unknown".
- insights: one object per finding; risk_type "none" for data-quality findings; estimated_delay_days is
  your best estimate of added delay in whole days (0 if none). Use MULTIPLE_RISKS when two or more risk
  factors are Medium or higher."""


def _enum(values):
    return {"type": "STRING", "enum": values}


RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "risk_factors": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "type": _enum(ALLOWED_RISK_TYPES), "severity": _enum(ALLOWED_SEVERITY), "detail": {"type": "STRING"}},
            "required": ["type", "severity", "detail"]}},
        "primary_risk_factor": _enum(ALLOWED_RISK_TYPES),
        "affected_location": _enum(ALLOWED_LOCATIONS),
        "expected_impact": _enum(ALLOWED_IMPACT),
        "confidence_score": {"type": "NUMBER"},
        "sources": {"type": "ARRAY", "items": _enum(ALLOWED_SOURCES)},
        "conflicting_sources": {"type": "BOOLEAN"},
        "insights": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "code": _enum(INSIGHT_CODES), "risk_type": _enum(INSIGHT_RISK_TYPES), "severity": _enum(ALLOWED_SEVERITY),
            "location": _enum(ALLOWED_LOCATIONS), "estimated_delay_days": {"type": "INTEGER"}},
            "required": ["code", "risk_type", "severity", "location", "estimated_delay_days"]}},
    },
}
RESPONSE_SCHEMA["required"] = list(RESPONSE_SCHEMA["properties"])

# Safe default when the AI step fails: confidence 0 + MISSING_DATA sends the shipment to human review.
FALLBACK_AI_RESPONSE = {
    "risk_factors": [], "primary_risk_factor": "infrastructure_disruption", "affected_location": "Unknown",
    "expected_impact": "None", "confidence_score": 0.0, "sources": [], "conflicting_sources": True,
    "insights": [{"code": "MISSING_DATA", "risk_type": "none", "severity": "High",
                                           "location": "Route", "estimated_delay_days": 0}],
}

http_session = requests.Session()  # reuses connections across calls
log = logging.getLogger("ai_manager")
log.setLevel(logging.DEBUG)
if not log.handlers:
    handler = logging.FileHandler("app.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)


# ---------------- External feeds ----------------
def fill_coordinates(shipment):
    """Copy with upper-case port codes and missing lat/lon filled from the port reference (CSV rows)."""
    shipment = dict(shipment)
    for end in ("origin", "destination"):
        code = str(shipment.get(f"{end}_port", "")).strip().upper()
        shipment[f"{end}_port"] = code
        lat, lon = shipment.get(f"{end}_lat"), shipment.get(f"{end}_lon")
        if any(v is None or v == "" or v != v for v in (lat, lon)) and code in validator.PORTS_BY_CODE:
            shipment[f"{end}_lat"], shipment[f"{end}_lon"] = validator.port_coordinates(code)
    return shipment


def fetch_weather(lat, lon):
    """16 days of hourly wind/pressure/visibility (forecast API) and waves (marine API). Raises on failure."""
    common = {"latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 16}
    weather = http_session.get("https://api.open-meteo.com/v1/forecast", timeout=HTTP_TIMEOUT, params={
        **common, "hourly": "wind_speed_10m,wind_gusts_10m,pressure_msl,visibility", "cell_selection": "sea"})
    marine = http_session.get("https://marine-api.open-meteo.com/v1/marine", timeout=HTTP_TIMEOUT, params={
        **common, "hourly": "wave_height,swell_wave_height,wave_period"})
    return {**weather.json()["hourly"], **marine.json()["hourly"]}


def fetch_news(shipment):
    """Recent English GDELT headlines about risks at either port; None if the feed fails."""
    time.sleep(5)  # GDELT allows one request every 5 seconds
    names = [validator.PORTS_BY_CODE[shipment[f"{end}_port"]]["name"] for end in ("origin", "destination")]
    query = (f'("{names[0]}" OR "{names[1]}") '
             '(piracy OR "armed robbery" OR "port congestion" OR strike OR protest OR unrest) sourcelang:english')
    try:
        articles = http_session.get("https://api.gdeltproject.org/api/v2/doc/doc", timeout=HTTP_TIMEOUT, params={
            "query": query, "mode": "ArtList", "maxrecords": 8, "format": "json", "timespan": "3d"}).json()
        return [{"title": a["title"], "seen": a["seendate"]} for a in articles.get("articles", [])]
    except Exception as exc:  # any network/JSON problem: log it, never stop the run
        log.warning("news feed failed for %s: %s", shipment.get("shipment_id"), exc)
        return None


def gather_external(shipment):
    """Weather at both ends + news; a failed feed is logged and stored as None."""
    external = {"weather": {}, "news": None}
    for end in ("origin", "destination"):
        try:
            external["weather"][end] = fetch_weather(shipment[f"{end}_lat"], shipment[f"{end}_lon"])
        except Exception as exc:
            log.warning("weather feed failed for %s %s: %s", shipment.get("shipment_id"), end, exc)
            external["weather"][end] = None
    if all(shipment.get(f"{end}_port") in validator.PORTS_BY_CODE for end in ("origin", "destination")):
        external["news"] = fetch_news(shipment)
    return external


# ---------------- Gemini ----------------
def call_gemini(shipment, external):
    """Ask Gemini for the coded assessment, retrying network errors with a growing delay."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    prompt = "SHIPMENT:\n" + json.dumps(shipment, default=str) + "\n\nEXTERNAL DATA:\n" + json.dumps(external, default=str)
    body = {"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "seed": 0, "responseMimeType": "application/json",
                                 "responseSchema": RESPONSE_SCHEMA}}
    delay = 1.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = http_session.post(GEMINI_URL, json=body, timeout=HTTP_TIMEOUT * 2,
                                  headers={"x-goog-api-key": key, "Content-Type": "application/json"})
            r.raise_for_status()
            return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as exc:
            log.warning("Gemini attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(delay * (1 + random.random()))  # wait longer each time, with jitter
            delay *= 2


# ---------------- Main entry point ----------------
def enrich_record(record):
    """One shipment: fetch the feeds, ask Gemini; FALLBACK_AI_RESPONSE on any failure."""
    shipment = fill_coordinates(record)
    external = gather_external(shipment)
    fetched_at = datetime.now().isoformat(timespec="seconds")
    try:
        result = call_gemini(shipment, external)
        if not all(k in result for k in RESPONSE_SCHEMA["required"]):
            raise ValueError("Gemini response missing required fields")
    except Exception as exc:
        log.error("AI assessment failed for %s: %s", shipment.get("shipment_id"), exc)
        result = dict(FALLBACK_AI_RESPONSE)
    return {**shipment, **result, "external_data_fetched_at": fetched_at}


def assess_shipments(shipments: pd.DataFrame) -> pd.DataFrame:
    """One row per shipment: the input columns + Gemini's coded fields + external_data_fetched_at."""
    return pd.DataFrame([enrich_record(s) for s in shipments.to_dict("records")])