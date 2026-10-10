"""
logic_manager.py
Business rules for the Logistics Risk Assessment System (Singapore).

Design notes (matches the four-manager flow):
  - LOGIC_MANAGER holds domain logic ONLY. No print(), no file access, no API calls.
  - It receives the AI Manager's validated JSON record (as a dict) and a
    DataManager-like object for history look-ups.
  - It returns a Decision object. IO_MANAGER displays it, DATA_MANAGER saves it.
  - The AI never makes the final decision. Every outcome is decided here.

Rule pipeline:
  Part 1  Validation checks
  Part 2  Operational decision making (Rules 1-5)
  Part 3  Escalation protocols (financial check, alerts, human review)
"""

from dataclasses import dataclass, field
from enum import IntEnum
from datetime import datetime, timedelta


# --------------------------------------------------------------------------
# Constants (change thresholds here, not inside the rules)
# --------------------------------------------------------------------------
class Level(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


LEVEL_FROM_TEXT = {"low": Level.LOW, "medium": Level.MEDIUM, "high": Level.HIGH}

CONFIDENCE_MIN = 0.60             # below this, AI output needs a human
HISTORY_WINDOW_DAYS = 21          # Rule 3 look-back
PERFECT_STORM_MIN_MEDIUMS = 3     # Rule 1
REROUTE_COST_LIMIT_PCT = 20.0     # Part 3 financial threshold
DATA_MAX_AGE_HOURS = 24           # external data older than this is "outdated"

PERFECT_STORM_FACTORS = {"weather", "port_congestion", "labor_shortage"}
INSURANCE_TRIGGERS = {"piracy_threat", "severe_civil_unrest"}

REQUIRED_FIELDS = [
    "shipment_id", "route_id", "origin", "destination", "transport_type",
    "transport_mode", "goods", "risk_factors", "primary_risk_factor",
    "affected_location", "expected_impact", "confidence_score", "sources",
]
