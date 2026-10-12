"""
logic_manager.py
Business rules for the Logistics Risk Assessment System (Singapore).

Design notes (matches the four-manager flow):
  - LOGIC_MANAGER holds domain logic ONLY. No print(), no file writes, no API calls.
  - It receives one row of ai_manager.assess_shipments() (shipment fields plus
    Gemini's response fields) and the list of saved records from
    data_manager.load_records() for history look-ups.
  - It returns a Decision object. IO_MANAGER displays it, DATA_MANAGER saves it
    (data_manager.add_record expects decision_to_dict(decision)).
  - The AI never makes the final decision. Every outcome is decided here.

Rule pipeline:
  Part 0  Prepare the AI row (route_id, port names, defaults for fields
          the IO Manager does not collect yet)
  Part 1  Validation checks
  Part 2  Operational decision making (Rules 1-5)
  Part 3  Escalation protocols (financial check, alerts, human review)
"""

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum

import data_manager
import validator


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
CARGO_DESTRUCTION_IMPACTS = {"cargo_destruction", "total_loss"}
NO_EVENT_VALUES = {"", "none", "n/a", "null", "nan"}

# The IO Manager currently only collects ports and dates, so these are the
# defaults until transport type / goods inputs are added.
DEFAULT_TRANSPORT_TYPE = "Cargo Vessel"
DEFAULT_TRANSPORT_MODE = "sea"

# Fields ai_manager.assess_shipments() always provides (shipment + AI schema).
REQUIRED_FIELDS = [
    "shipment_id", "origin_port", "destination_port",
    "risk_factors", "primary_risk_factor", "affected_location",
    "expected_impact", "confidence_score", "sources",
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
    alerts: list = field(default_factory=list)     # dicts: recipient / channels / message
    rationale: list = field(default_factory=list)  # audit trail (why each rule fired)


def decision_to_dict(decision):
    """Plain dict version of a Decision, in the shape data_manager.add_record expects."""
    return asdict(decision)


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------
def _level(text):
    """Convert 'Medium' / 'medium' / 'MEDIUM' into a Level. Unknown -> LOW."""
    return LEVEL_FROM_TEXT.get(str(text).strip().lower(), Level.LOW)


def _key(text):
    """Normalise labels like 'Piracy Threat' -> 'piracy_threat'."""
    return str(text).strip().lower().replace(" ", "_")


def _add_alert(decision, recipient, channels, message):
    decision.alerts.append(
        {"recipient": recipient, "channels": channels, "message": message}
    )


def _port_name(code):
    """Port code -> common name from the port reference (falls back to the code)."""
    port = validator.PORTS_BY_CODE.get(code)
    return port["name"] if port else str(code)


def _great_circle_km(lat1, lon1, lat2, lon2):
    """Straight-line (haversine) distance between two coordinates, in km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _as_datetime(value):
    """Accept a datetime or an ISO string; return None if it can't be read."""
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


# --------------------------------------------------------------------------
# PART 0: PREPARE THE AI MANAGER'S ROW
# --------------------------------------------------------------------------
def prepare_record(ai_record):
    """Return a copy of an AI Manager row with the extra fields the rules use.

    - route_id like "SGSIN-NLRTM" (what data_manager.get_route_history matches on)
    - origin / destination port names (used by data_manager.query_records text search)
    - transport_type / transport_mode / goods defaults (not collected by IO Manager yet)
    - baseline_distance_km from the port coordinates, if not already given
    - cleans pandas leftovers (NaN instead of a dict/list) in optional fields
    """
    record = dict(ai_record)
    origin = record.get("origin_port", "")
    destination = record.get("destination_port", "")

    record.setdefault("route_id", f"{origin}-{destination}")
    record.setdefault("origin", _port_name(origin))
    record.setdefault("destination", _port_name(destination))
    record.setdefault("transport_type", DEFAULT_TRANSPORT_TYPE)
    record.setdefault("transport_mode", DEFAULT_TRANSPORT_MODE)

    if not isinstance(record.get("goods"), dict):
        record["goods"] = {}
    if not isinstance(record.get("risk_factors"), list):
        record["risk_factors"] = []
    if not isinstance(record.get("alternative_route"), dict):
        record["alternative_route"] = None

    if not record.get("baseline_distance_km"):
        try:
            record["baseline_distance_km"] = round(_great_circle_km(
                float(record["origin_lat"]), float(record["origin_lon"]),
                float(record["destination_lat"]), float(record["destination_lon"]),
            ), 1)
        except (KeyError, TypeError, ValueError):
            record["baseline_distance_km"] = None

    return record


# --------------------------------------------------------------------------
# PART 1: VALIDATION CHECKS (data consistency and completeness)
# --------------------------------------------------------------------------
def validate_record(record, decision, now):
    """Return True if the record is safe to run through the rules."""
    # An empty risk_factors list is valid (the AI found no risks), so only
    # None / "" count as missing here.
    missing = [f for f in REQUIRED_FIELDS if record.get(f) in (None, "")]
    if missing:
        decision.outcome = "REJECT"
        decision.needs_human = True
        decision.flags.append("Incomplete AI record")
        decision.rationale.append(f"Validation failed: missing fields {missing}")
        return False

    confidence = record["confidence_score"]
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not 0.0 <= confidence <= 1.0):
        decision.outcome = "REJECT"
        decision.needs_human = True
        decision.flags.append("Invalid confidence score")
        decision.rationale.append("Validation failed: confidence_score not in 0-1")
        return False

    # Softer problems: keep going, but a human must look at it
    if confidence < CONFIDENCE_MIN:
        decision.needs_human = True
        decision.flags.append("Low AI confidence")
        decision.rationale.append(
            f"Confidence {confidence:.2f} is below {CONFIDENCE_MIN:.2f}"
        )

    fetched_at = _as_datetime(record.get("external_data_fetched_at")) \
        if record.get("external_data_fetched_at") else None
    if fetched_at and now - fetched_at > timedelta(hours=DATA_MAX_AGE_HOURS):
        decision.needs_human = True
        decision.flags.append("Outdated external data")
        decision.rationale.append(f"External data is older than {DATA_MAX_AGE_HOURS}h")

    if record.get("conflicting_sources") is True:
        decision.needs_human = True
        decision.flags.append("Conflicting sources")
        decision.rationale.append("AI reported conflicting or missing information")

    return True


# --------------------------------------------------------------------------
# PART 2: OPERATIONAL DECISION MAKING
# --------------------------------------------------------------------------
def rule_perfect_storm(record, decision):
    """
    Rule 1: several smaller risks combine into one emergency.
    Medium Weather + Medium Port Congestion + Medium Labor Shortage -> High Risk.
    """
    # Keep the highest severity if the AI lists the same type twice
    levels = {}
    for r in record["risk_factors"]:
        k = _key(r.get("type", ""))
        levels[k] = max(levels.get(k, Level.LOW), _level(r.get("severity")))

    if any(lv == Level.HIGH for lv in levels.values()):
        decision.overall_risk = "High"
        decision.rationale.append("Rule 1: at least one risk factor is High")

    mediums = [f for f in PERFECT_STORM_FACTORS if levels.get(f, Level.LOW) >= Level.MEDIUM]
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
    factor_keys = {_key(r.get("type", "")) for r in record["risk_factors"]}
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
                f"Rule 2: Severe Crosswinds noted, {record['transport_type']} already suitable"
            )


def rule_dynamic_insurance(record, decision):
    """
    Rule 4: Piracy Threat or Severe Civil Unrest -> update financial profile
    and hold until a human confirms extended insurance was bought.
    """
    factor_keys = {_key(r.get("type", "")) for r in record["risk_factors"]}
    triggered = INSURANCE_TRIGGERS & (factor_keys | {_key(record["primary_risk_factor"])})

    if triggered:
        decision.hold_shipment = True
        decision.needs_human = True
        decision.flags.append("Premium Increase Required")
        decision.actions.append("Update financial profile: extended insurance needed")
        decision.rationale.append(
            f"Rule 4: {', '.join(sorted(triggered))} detected, holding until insurance confirmed"
        )
        decision.overall_risk = "High"


def rule_low_risk_validation(record, decision, db_records, now):
    """
    Rule 3: never auto-approve a 'Low' route that recently failed.
    Ask the Data Manager for the last 21 days of saved records on this exact route.
    """
    if decision.overall_risk != "Low":
        return

    since = now - timedelta(days=HISTORY_WINDOW_DAYS)
    try:
        past = data_manager.get_route_history(db_records, record["route_id"], since)
    except (KeyError, TypeError, ValueError) as exc:
        decision.needs_human = True
        decision.flags.append("Route history unavailable")
        decision.rationale.append(f"Rule 3: could not read route history ({exc}), needs human")
        return

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


def _affects_origin(record):
    """True if the AI's affected_location refers to the origin port (code or name)."""
    location = _key(record["affected_location"])
    origin_keys = {_key(record["origin_port"]), _key(record["origin"])}
    return any(k and k in location for k in origin_keys)


def rule_inventory_replacement(record, decision):
    """
    Rule 5: cargo likely destroyed by a sudden extreme event
    (e.g. Category 5 hurricane at the origin port) -> Procurement Alert.
    Do not just stop the shipment: tell the company to reorder now.
    """
    impact = _key(record["expected_impact"])
    event = str(record.get("extreme_event") or "").strip()
    has_event = event.lower() not in NO_EVENT_VALUES

    if impact in CARGO_DESTRUCTION_IMPACTS and has_event and _affects_origin(record):
        goods = record["goods"].get("description", "the goods on this shipment")
        decision.hold_shipment = True
        decision.flags.append("Procurement Alert")
        decision.actions.append(f"Reorder goods immediately: {goods} (extreme event: {event})")
        _add_alert(
            decision, "procurement_team", ["email", "sms"],
            f"Shipment {record['shipment_id']} is at risk of destruction. "
            f"Consider reordering to avoid stock-out.",
        )
        decision.rationale.append("Rule 5: cargo destruction predicted from an extreme event at origin")


def decide_outcome(record, decision):
    """Turn the accumulated flags into one final operational outcome."""
    if decision.outcome == "REJECT":
        return

    goods = record["goods"]
    time_sensitive = goods.get("perishable") or goods.get("time_sensitive")
    alternative = record.get("alternative_route")

    if "Procurement Alert" in decision.flags:
        decision.outcome = "DELAY"
    elif "Premium Increase Required" in decision.flags:
        decision.outcome = "INSURE"
    elif decision.overall_risk == "High":
        # Prefer rerouting for time-sensitive cargo, otherwise delay the departure
        if time_sensitive and alternative and alternative.get("name"):
            decision.outcome = "REROUTE"
            decision.actions.append(f"Reroute via {alternative['name']}")
        else:
            decision.outcome = "DELAY"
            decision.actions.append("Delay departure until conditions clear")
        decision.needs_human = True
    elif decision.overall_risk == "Medium":
        decision.outcome = "PROCEED"
        decision.actions.append("Proceed with monitoring")
    else:
        decision.outcome = "PROCEED"

    # Anything held for a human is not fully automatic
    if decision.hold_shipment and decision.outcome == "PROCEED":
        decision.outcome = "ESCALATE"


# --------------------------------------------------------------------------
# PART 3: ESCALATION PROTOCOLS
# --------------------------------------------------------------------------
def check_financial_threshold(record, decision):
    """
    If an automated reroute adds more than 20% distance, stop the auto-reroute
    and send an 'Excessive Cost' alert to the Operations Director.
    """
    if decision.outcome != "REROUTE":
        return

    base = record.get("baseline_distance_km")
    new = (record.get("alternative_route") or {}).get("distance_km")
    if not base or not new:
        decision.needs_human = True
        decision.flags.append("Reroute distance unknown")
        decision.rationale.append("Financial check: cannot compare distances, needs human")
        return

    increase_pct = (new - base) / base * 100
    if increase_pct > REROUTE_COST_LIMIT_PCT:
        decision.outcome = "ESCALATE"
        decision.hold_shipment = True
        decision.needs_human = True
        decision.flags.append("Excessive Cost")
        decision.actions = [a for a in decision.actions if not a.startswith("Reroute")]
        decision.actions.append("Automatic rerouting stopped")
        _add_alert(
            decision, "operations_director", ["email"],
            f"Excessive Cost: reroute for {record['shipment_id']} adds "
            f"{increase_pct:.1f}% distance (limit {REROUTE_COST_LIMIT_PCT:.0f}%).",
        )
        decision.rationale.append(
            f"Financial check: reroute +{increase_pct:.1f}% > {REROUTE_COST_LIMIT_PCT:.0f}%, stopped"
        )
    else:
        decision.rationale.append(
            f"Financial check: reroute +{increase_pct:.1f}% is within the limit"
        )


def stakeholder_alerting(record, decision):
    """
    Stakeholder Alerting: a High risk shipment sends an urgent SMS and email
    to the cargo owner and the active supply chain manager, including the
    AI's summarised insights.
    """
    if decision.overall_risk != "High":
        return

    insights = record.get("insights") or []
    summary = (
        f"URGENT: shipment {record['shipment_id']} ({record['origin']} -> "
        f"{record['destination']}) is HIGH RISK. "
        f"Main risk: {record['primary_risk_factor']} at {record['affected_location']}. "
        f"Expected impact: {record['expected_impact']}. "
        f"Recommended: {decision.outcome}."
    )
    if insights:
        summary += " AI summary: " + " ".join(str(i) for i in insights[:3])

    for recipient in ("cargo_owner", "supply_chain_manager"):
        _add_alert(decision, recipient, ["sms", "email"], summary)


def escalation_protocol(decision):
    """Final gate: anything needing a human is never marked as fully automatic."""
    if decision.needs_human and decision.outcome == "PROCEED":
        decision.outcome = "ESCALATE"
    if decision.needs_human:
        decision.actions.append("Route to human review queue")


# --------------------------------------------------------------------------
# MAIN ENTRY POINTS
# --------------------------------------------------------------------------
def evaluate_shipment(ai_record, db_records, now=None):
    """
    Run one AI Manager row through every rule.

    ai_record  - one row of ai_manager.assess_shipments() as a dict
    db_records - list from data_manager.load_records(data_manager.DB_FILE)

    Returns (record, decision): the prepared record (with route_id, origin,
    destination, ...) and its Decision, ready for
    data_manager.add_record(file, db_records, record, decision_to_dict(decision)).
    """
    now = now or datetime.now()
    record = prepare_record(ai_record)  # copy, never mutates the caller's data
    decision = Decision(shipment_id=str(record.get("shipment_id", "UNKNOWN")))

    # Part 1
    if not validate_record(record, decision, now):
        return record, decision

    # Part 2 (Rule 4 runs before Rule 3 so insurance risks are never "Low")
    rule_perfect_storm(record, decision)
    rule_asset_reallocation(record, decision)
    rule_dynamic_insurance(record, decision)
    rule_low_risk_validation(record, decision, db_records, now)
    rule_inventory_replacement(record, decision)
    decide_outcome(record, decision)

    # Part 3
    check_financial_threshold(record, decision)
    stakeholder_alerting(record, decision)
    escalation_protocol(decision)

    return record, decision


def evaluate_shipments(assessments, db_records, now=None):
    """Evaluate every row of ai_manager.assess_shipments() (a DataFrame).

    Returns a list of (record, decision) pairs in the same order as the rows.
    """
    return [evaluate_shipment(row, db_records, now) for row in assessments.to_dict("records")]


# --------------------------------------------------------------------------
# Demo (print() here is only for testing; display belongs to IO_MANAGER)
# --------------------------------------------------------------------------
if __name__ == "__main__":
    now = datetime(2026, 9, 28, 9, 0)

    # Same shape as an ai_manager.assess_shipments() row
    base = {
        "shipment_id": "SHP-001",
        "origin_port": "SGSIN", "origin_lat": 1.266667, "origin_lon": 103.833333,
        "destination_port": "NLRTM", "destination_lat": 51.933333, "destination_lon": 4.133333,
        "departure_time": "01/10/2026", "arrival_time": "30/10/2026",
        "primary_risk_factor": "weather", "affected_location": "Strait of Malacca",
        "expected_impact": "Delay", "confidence_score": 0.82,
        "sources": ["Open-Meteo", "GDELT"], "conflicting_sources": False,
        "extreme_event": "None", "insights": ["Moderate swell expected near Malacca."],
        "alternative_route": None,
    }

    cases = {
        "Perfect Storm": {
            **base, "shipment_id": "SHP-001",
            "risk_factors": [
                {"type": "weather", "severity": "Medium", "detail": "Heavy rain"},
                {"type": "port_congestion", "severity": "Medium", "detail": "Queues"},
                {"type": "labor_shortage", "severity": "Medium", "detail": "Strike talk"},
            ],
            "goods": {"description": "Fresh fruit", "perishable": True},
            "alternative_route": {"name": "Cape of Good Hope", "distance_km": 20000},
        },
        "Piracy": {
            **base, "shipment_id": "SHP-002", "primary_risk_factor": "piracy_threat",
            "risk_factors": [{"type": "piracy_threat", "severity": "High", "detail": "ReCAAP alert"}],
        },
        "Low risk but bad history": {
            **base, "shipment_id": "SHP-003",
            "risk_factors": [{"type": "weather", "severity": "Low", "detail": "Light rain"}],
        },
        "AI fallback response": {
            **base, "shipment_id": "SHP-004", "risk_factors": [],
            "confidence_score": 0.0, "conflicting_sources": True,
            "primary_risk_factor": "infrastructure_disruption", "affected_location": "Unknown",
            "expected_impact": "None",
        },
        "Bad AI record": {"shipment_id": "SHP-005"},
    }

    # Same shape as records saved by data_manager.add_record
    db_records = [{
        "route_id": "SGSIN-NLRTM",
        "saved_at": (now - timedelta(days=10)).isoformat(),
        "flagged": False, "delayed": True,
    }]

    for name, rec in cases.items():
        _, d = evaluate_shipment(rec, db_records, now)
        print(f"\n=== {name} ===")
        print("Outcome :", d.outcome, "| Risk:", d.overall_risk, "| Human:", d.needs_human)
        print("Flags   :", d.flags)
        print("Actions :", d.actions)
        print("Alerts  :", [(a["recipient"], a["channels"]) for a in d.alerts])
        for line in d.rationale:
            print("  -", line)