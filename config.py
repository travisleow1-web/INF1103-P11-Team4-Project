import os
import json
import validator

CACHE_FILE = "ai_cache.json"
MAX_RETRIES = 3
HTTP_TIMEOUT = 20
HISTORY_DAYS = 90  # shipments that departed this recently get historical weather
TIMEZONE = "Asia/Singapore"
SCHEMA_VERSION = 2

SHIPMENT_FIELDS = (
    "shipment_id", "origin_port", "origin_lat", "origin_lon",
    "destination_port", "destination_lat", "destination_lon",
    "departure_time", "arrival_time",
)

with open("waypoints_reference.json", encoding="utf-8") as f:
    WAYPOINT_NAMES = [w["name"] for w in json.load(f)["waypoints"]]

ALLOWED_RISK_TYPES = [
    "weather", "severe_crosswinds", "port_congestion", "labor_shortage",
    "piracy_threat", "severe_civil_unrest", "geopolitical",
    "infrastructure_disruption",
]
ALLOWED_SEVERITY = ["Low", "Medium", "High"]
ALLOWED_IMPACT = ["Delay", "Cost Increase", "Cargo Damage", "Cargo Destruction", "None"]

ALLOWED_LOCATIONS = sorted(validator.PORTS_BY_CODE) + WAYPOINT_NAMES + ["Route", "Unknown"]

ALLOWED_EXTREME_EVENTS = [
    "none", "typhoon", "hurricane", "cyclone", "earthquake", "tsunami",
    "port_closure", "vessel_collision", "armed_attack", "other",
]

ALLOWED_SOURCES = ["open_meteo_weather", "open_meteo_marine", "open_meteo_historical_forecast",
                   "open_meteo_historical_weather", "gdelt_news", "shipment_data"]

INSIGHT_CODES = [
    "POTENTIAL_DELAY", "MULTIPLE_RISKS", "EXTREME_EVENT",
    "CONFLICTING_DATA", "OUTDATED_DATA", "MISSING_DATA", "NEEDS_HUMAN_REVIEW",
]
INSIGHT_RISK_TYPES = ALLOWED_RISK_TYPES + ["none"]

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

SYSTEM_PROMPT = """You are a logistics risk analyst for shipments passing through or destined for Singapore.
Your role is exclusively to analyse, structure, and quantify risk factors from provided feeds.
You NEVER decide operational actions (such as proceed, delay, reroute, or insure): downstream business rules execute those.

Rules:
- Identify ALL distinct risk factors present across the data. Do NOT omit moderate or low risks.
- Use ONLY the shipment data and external data provided. Do not invent facts.
- For shipments that already departed, weather covers the departure-to-arrival dates: historical forecast data
  (hourly keys) plus "historical_weather" (reanalysis; visibility is null). Judge what the shipment experienced.
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

FALLBACK_AI_RESPONSE = {
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