import json
import logging
import os
from datetime import datetime, timedelta

from dataclasses import dataclass, field
from enum import IntEnum


DB_FILE = "shipments.json"
PROCESSED_FILE = "processed_shipments.json"  # per shipment: input row, weather, news, AI response

def load_records(file_path):
    """Startup: load all records."""
    try:
      with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
    except FileNotFoundError: #File Doesn't exist or is missing
      return []
    except (json.JSONDecodeError, OSError) as exc: #File is corrupted or any other errors
      return []

def save_records(db_records, file_path):
  """End of Program: save all records."""
  with open(file_path, "w", encoding="utf-8") as f:
    json.dump(db_records, f, indent=2)

def add_record(file_path, db_records, record, decision):
  """decision is a dict. Stores both, plus fields used for history look-ups."""

  entry = {
    **record,
    "decision": decision,
    "saved_at": datetime.now().isoformat(),
    "flagged": decision["needs_human"] or decision["overall_risk"] != "Low",
    "delayed": decision["outcome"] == "DELAY",
  }
  db_records.append(json.loads(json.dumps(entry, default=str)))
  save_records(db_records, file_path)

def get_route_history(db_records, route_id, since):
  """Used by Logic Manager Rule 3 (last 21 days on the same route)."""
  out = []
  for r in db_records:
    if r.get("route_id") != route_id:
      continue
    saved = datetime.fromisoformat(r["saved_at"])
    if saved >= since:
      out.append({"date": saved, "flagged": r["flagged"], "delayed": r["delayed"]})
  return out

def query_records(db_records, filter):
  """Used by IO Manager filter/query."""
  risk = filter.get("risk")
  outcome = filter.get("outcome")
  needs_human = filter.get("needs_human")
  text = filter.get("text")
  text_lower = text.lower() if text else None

  # Fast-path: if no filters applied, return shallow full list
  if not (risk or outcome or (needs_human is not None) or text_lower):
    return db_records

  result = []
  for r in db_records:
    decision = r["decision"]

    matched_record = (
        #filtered criteria is not empty and record matches criteria
        (risk and decision.get("overall_risk") == risk) or 
        (outcome and decision.get("outcome") == outcome) or 
        (needs_human is not None and decision.get("needs_human") == needs_human) or
        (text_lower and (text_lower in r["origin"].lower() or text_lower in r["destination"].lower()))
    )
    if matched_record:
        result.append(r)

  return result

records = load_records(DB_FILE)
# --------------------------------------------------------------------------
# Constants (change thresholds here, not inside the rules)
# --------------------------------------------------------------------------
class Level(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


#PHUC TO COMMIT OVER HERE (just to add something into github)
LEVEL_FROM_TEXT = {"low": Level.LOW, "medium": Level.MEDIUM, "high": Level.HIGH}

CONFIDENCE_MIN = 0.60             # below this, AI output needs a human
HISTORY_WINDOW_DAYS = 21          # Rule 4 look-back
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

# --------------------------------------------------------------------------
# Output object 
# --------------------------------------------------------------------------
@dataclass
class Decision:
    shipment_id: str
    overall_risk: str = "Low"
    outcome: str = "PROCEED"      # PROCEED / DELAY / REROUTE / INSURE / ESCALATE / REJECT
    hold_shipment: bool = False
    needs_human: bool = False
    flags: list = field(default_factory=list)      # e.g. "Premium Increase Required"
    actions: list = field(default_factory=list)    # business actions to carry out
    alerts: list = field(default_factory=list)     # dicts: who / channel / message
    rationale: list = field(default_factory=list)  # audit trail (why each rule fired)



# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------
def _level(text):
    """Convert 'Medium' / 'medium' / 'MEDIUM' into a Level. Unknown -> LOW."""
    return LEVEL_FROM_TEXT.get(str(text).strip().lower(), Level.LOW)

def _key(text):
    """Normalise labels like 'Piracy Threat' -> 'piracy_threat'."""
    return str(text).strip().lower().replace(" ", "_")




# --------------------------------------------------------------------------
# PART 2: OPERATIONAL DECISION MAKING
# --------------------------------------------------------------------------

def rule_perfect_storm(record, decision):
    """
    Rule 1: several smaller risks combine into one emergency.
    Medium Rain + Medium Port Congestion + Medium Labor Shortage -> High Risk.
    """
    levels = {_key(r["type"]): _level(r["severity"]) for r in record["risk_factors"]}

    # Any single High factor already makes the shipment High risk
    if any(lv == Level.HIGH for lv in levels.values()):
        decision.overall_risk = "High"
        decision.rationale.append("Rule 1: at least one risk factor is High")

    mediums = [
        f for f in PERFECT_STORM_FACTORS
        if levels.get(f, Level.LOW) >= Level.MEDIUM
    ]
    if len(mediums) >= PERFECT_STORM_MIN_MEDIUMS:
        decision.overall_risk = "High"
        decision.flags.append("Perfect Storm")
        decision.rationale.append(
            f"Rule 1 (Perfect Storm): {', '.join(sorted(mediums))} all >= Medium, upgraded to High"
        )
    elif decision.overall_risk != "High" and any(lv == Level.MEDIUM for lv in levels.values()):
        decision.overall_risk = "Medium"

def rule_asset_reallocation(record, decision):
    """
    Rule 2: Severe Crosswinds on a Light Freight vehicle -> reassign to Heavy Freight.
    """
    factor_keys = {_key(r["type"]) for r in record["risk_factors"]}
    primary = _key(record["primary_risk_factor"])

    if "severe_crosswinds" in factor_keys or primary == "severe_crosswinds":
        if record["transport_type"] == "Light Freight":
            record["transport_type"] = "Heavy Freight"
            decision.actions.append("Reassign load to a Heavy Freight carrier")
            decision.flags.append("Asset Reallocated")
            decision.rationale.append(
                "Rule 2: Severe Crosswinds + Light Freight, moved to Heavy Freight (rollover risk)"
            )
        else:
            decision.rationale.append(
                "Rule 2: Severe Crosswinds noted, transport already suitable"
            )

def rule_low_risk_validation(record, decision, data_manager, now):
    """
    Rule 3: never auto-approve a 'Low' route that recently failed.
    Ask the Data Manager for the last 21 days of logs on this exact route.
    """
    if decision.overall_risk != "Low":
        return

    since = now - timedelta(days=HISTORY_WINDOW_DAYS)
    past = data_manager.get_route_history(record["route_id"], since)
    problem_runs = [p for p in past if p.get("flagged") or p.get("delayed")]

    if problem_runs:
        decision.needs_human = True
        decision.hold_shipment = True
        decision.flags.append("Cautionary Override")
        decision.actions.append("Require human dispatcher sign-off")
        decision.rationale.append(
            f"Rule 3: AI says Low but {len(problem_runs)} shipment(s) on route "
            f"{record['route_id']} were flagged or delayed in the last {HISTORY_WINDOW_DAYS} days"
        )
    else:
        decision.rationale.append("Rule 3: Low risk and clean 21-day history, auto-approve")

