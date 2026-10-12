"""
logic_manager.py
Business rules for the Logistics Risk Assessment System (Singapore).

Design notes (matches the four-manager flow):
  - LOGIC_MANAGER holds domain logic ONLY. No print(), no file writes, no API calls.
  - It receives one row of ai_manager.assess_shipments() (shipment fields plus
    Gemini's structured response fields) and the list of saved records from
    data_manager.load_records() for history look-ups.
  - Every AI value is a fixed code (risk types, severities, port codes,
    insight codes ...). The allowed values are imported from ai_manager, so
    both managers always use the same field inputs.
  - It returns a decision dict (see new_decision). IO_MANAGER displays it, DATA_MANAGER saves it
    (data_manager.add_record expects decision_to_dict(decision)).
  - The AI never makes the final decision. Every outcome is decided here.

AI fields used (one row of ai_manager.assess_shipments()):
  risk_factors[]       {type, severity, location, source, detail}
  primary_risk_factor  ALLOWED_RISK_TYPES
  affected_location    ALLOWED_LOCATIONS (port code / waypoint / Route / Unknown)
  expected_impact      ALLOWED_IMPACT
  confidence_score     0.0 - 1.0
  sources[]            ALLOWED_SOURCES
  conflicting_sources  bool
  extreme_event        ALLOWED_EXTREME_EVENTS
  insights[]           {code, risk_type, severity, location, estimated_delay_days}
  alternative_route    {name (waypoint), distance_km} or None
  external_data_fetched_at  ISO timestamp

Rule pipeline:
  Part 0  Prepare the AI row (route_id, port names, defaults for fields
          the IO Manager does not collect yet)
  Part 1  Validation checks (required fields, confidence, schema values, data age)
  Part 2  Operational decision making (Rules 1-5, plus Rule 1b for AI insights)
  Part 3  Escalation protocols (financial check, alerts, human review)
"""

import copy
import math
from datetime import datetime, timedelta

import data_manager
import validator
from ai_manager import (
    ALLOWED_EXTREME_EVENTS,
    ALLOWED_IMPACT,
    ALLOWED_LOCATIONS,
    ALLOWED_RISK_TYPES,
    ALLOWED_SEVERITY,
    INSIGHT_CODES,
    INSIGHT_RISK_TYPES,
)


# --------------------------------------------------------------------------
# Constants (change thresholds here, not inside the rules)
# --------------------------------------------------------------------------
# Severity levels as plain numbers so they can be compared (HIGH > MEDIUM)
LOW, MEDIUM, HIGH = 1, 2, 3

LEVEL_FROM_TEXT = {"low": LOW, "medium": MEDIUM, "high": HIGH}

CONFIDENCE_MIN = 0.60             # below this, AI output needs a human
HISTORY_WINDOW_DAYS = 21          # Rule 3 look-back
PERFECT_STORM_MIN_MEDIUMS = 3     # Rule 1
REROUTE_COST_LIMIT_PCT = 20.0     # Part 3 financial threshold
DATA_MAX_AGE_HOURS = 24           # external data older than this is "outdated"
DELAY_DAYS_LIMIT = 3              # Rule 1b: AI-estimated delay >= this -> at least Medium
DELAY_DAYS_HIGH = 7               # Rule 1b: ... and >= this -> High

# Rule inputs, written with the exact values the AI is allowed to return
PERFECT_STORM_FACTORS = {"weather", "port_congestion", "labor_shortage"}
INSURANCE_TRIGGERS = {"piracy_threat", "severe_civil_unrest"}
CROSSWIND_FACTOR = "severe_crosswinds"
CARGO_DESTRUCTION_IMPACTS = {"Cargo Destruction"}
NO_EXTREME_EVENT = "none"
DATA_QUALITY_INSIGHTS = {"CONFLICTING_DATA", "OUTDATED_DATA", "MISSING_DATA", "NEEDS_HUMAN_REVIEW"}

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
def new_decision(shipment_id):
    """Return a fresh decision for one shipment, as a plain dict.

    Keys:
      shipment_id    str
      overall_risk   "Low" / "Medium" / "High"
      outcome        PROCEED / DELAY / REROUTE / INSURE / ESCALATE / REJECT
      hold_shipment  bool
      needs_human    bool
      flags          list of str, e.g. "Premium Increase Required"
      actions        list of str, business actions to carry out
      alerts         list of dicts: recipient / channels / message
      rationale      list of str, audit trail (why each rule fired)
    """
    return {
        "shipment_id": shipment_id,
        "overall_risk": "Low",
        "outcome": "PROCEED",
        "hold_shipment": False,
        "needs_human": False,
        "flags": [],
        "actions": [],
        "alerts": [],
        "rationale": [],
    }


def decision_to_dict(decision):
    """Independent copy of a decision, in the shape data_manager.add_record expects."""
    return copy.deepcopy(decision)


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------
def _level(text):
    """Convert 'Medium' / 'medium' / 'MEDIUM' into 1-3. Unknown -> LOW."""
    return LEVEL_FROM_TEXT.get(str(text).strip().lower(), LOW)


def _add_alert(decision, recipient, channels, message):
    decision["alerts"].append(
        {"recipient": recipient, "channels": channels, "message": message}
    )


def _add_flag(decision, flag):
    if flag not in decision["flags"]:
        decision["flags"].append(flag)


def _raise_risk(decision, level):
    """Raise overall_risk to level ("Medium" or "High"), never lower it."""
    if _level(level) > _level(decision["overall_risk"]):
        decision["overall_risk"] = level


def _port_name(code):
    """Port code -> common name from the port reference (falls back to the value itself)."""
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


def _describe_insight(insight):
    """Compact label for an insight, e.g. 'POTENTIAL_DELAY weather/High @CNSHA +8d'."""
    text = f"{insight['code']} {insight['risk_type']}/{insight['severity']} @{insight['location']}"
    if insight["estimated_delay_days"]:
        text += f" +{insight['estimated_delay_days']}d"
    return text


# --------------------------------------------------------------------------
# PART 0: PREPARE THE AI MANAGER'S ROW
# --------------------------------------------------------------------------
def _clean_list(value, required_keys):
    """Keep only dict items that have every required key (drops NaN / strings)."""
    if not isinstance(value, list):
        return [], 0
    good = [i for i in value if isinstance(i, dict) and all(k in i for k in required_keys)]
    return good, len(value) - len(good)


def prepare_record(ai_record):
    """Return a copy of an AI Manager row with the extra fields the rules use.

    - route_id like "SGSIN-NLRTM" (what data_manager.get_route_history matches on)
    - origin / destination port names (used by data_manager.query_records text search)
    - transport_type / transport_mode / goods defaults (not collected by IO Manager yet)
    - baseline_distance_km from the port coordinates, if not already given
    - cleans pandas leftovers (NaN instead of a dict/list) in optional fields
    - drops malformed risk_factors / insights items; the count is kept in
      _dropped_items so validation can flag it
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
    if not isinstance(record.get("alternative_route"), dict):
        record["alternative_route"] = None
    if not isinstance(record.get("sources"), list):
        record["sources"] = []

    record["risk_factors"], bad_factors = _clean_list(
        record.get("risk_factors"), ("type", "severity"))
    record["insights"], bad_insights = _clean_list(
        record.get("insights"), ("code", "risk_type", "severity", "location", "estimated_delay_days"))
    for ins in record["insights"]:
        try:
            ins["estimated_delay_days"] = max(0, int(ins["estimated_delay_days"]))
        except (TypeError, ValueError):
            ins["estimated_delay_days"] = 0
    record["_dropped_items"] = bad_factors + bad_insights

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
def _schema_problems(record):
    """List every AI value that is not one of the shared allowed values."""
    problems = []
    checks = [
        ("primary_risk_factor", record.get("primary_risk_factor"), ALLOWED_RISK_TYPES),
        ("affected_location", record.get("affected_location"), ALLOWED_LOCATIONS),
        ("expected_impact", record.get("expected_impact"), ALLOWED_IMPACT),
        ("extreme_event", record.get("extreme_event", NO_EXTREME_EVENT), ALLOWED_EXTREME_EVENTS),
    ]
    for f in record["risk_factors"]:
        checks.append(("risk_factors.type", f["type"], ALLOWED_RISK_TYPES))
        checks.append(("risk_factors.severity", f["severity"], ALLOWED_SEVERITY))
    for i in record["insights"]:
        checks.append(("insights.code", i["code"], INSIGHT_CODES))
        checks.append(("insights.risk_type", i["risk_type"], INSIGHT_RISK_TYPES))
        checks.append(("insights.severity", i["severity"], ALLOWED_SEVERITY))
    for name, value, allowed in checks:
        if value not in allowed:
            problems.append(f"{name}={value!r}")
    if record["_dropped_items"]:
        problems.append(f"{record['_dropped_items']} malformed list item(s) dropped")
    return problems


def validate_record(record, decision, now):
    """Return True if the record is safe to run through the rules."""
    # An empty risk_factors list is valid (the AI found no risks), so only
    # None / "" count as missing here.
    missing = [f for f in REQUIRED_FIELDS if record.get(f) in (None, "")]
    if missing:
        decision["outcome"] = "REJECT"
        decision["needs_human"] = True
        decision["flags"].append("Incomplete AI record")
        decision["rationale"].append(f"Validation failed: missing fields {missing}")
        return False

    confidence = record["confidence_score"]
    if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
            or not 0.0 <= confidence <= 1.0):
        decision["outcome"] = "REJECT"
        decision["needs_human"] = True
        decision["flags"].append("Invalid confidence score")
        decision["rationale"].append("Validation failed: confidence_score not in 0-1")
        return False

    # Softer problems: keep going, but a human must look at it
    problems = _schema_problems(record)
    if problems:
        decision["needs_human"] = True
        decision["flags"].append("AI output outside schema")
        decision["rationale"].append(f"Validation: unexpected AI values {problems}")

    if confidence < CONFIDENCE_MIN:
        decision["needs_human"] = True
        decision["flags"].append("Low AI confidence")
        decision["rationale"].append(f"Confidence {confidence:.2f} is below {CONFIDENCE_MIN:.2f}")

    fetched_at = _as_datetime(record.get("external_data_fetched_at")) \
        if record.get("external_data_fetched_at") else None
    if fetched_at and now - fetched_at > timedelta(hours=DATA_MAX_AGE_HOURS):
        decision["needs_human"] = True
        decision["flags"].append("Outdated external data")
        decision["rationale"].append(f"External data is older than {DATA_MAX_AGE_HOURS}h")

    if record.get("conflicting_sources") is True:
        decision["needs_human"] = True
        decision["flags"].append("Conflicting sources")
        decision["rationale"].append("AI reported conflicting or missing information")

    return True


# --------------------------------------------------------------------------
# PART 2: OPERATIONAL DECISION MAKING
# --------------------------------------------------------------------------
def rule_perfect_storm(record, decision):
    """
    Rule 1: several smaller risks combine into one emergency.
    Medium weather + Medium port_congestion + Medium labor_shortage -> High Risk.
    """
    # Keep the highest severity if the AI lists the same type twice
    levels = {}
    for r in record["risk_factors"]:
        levels[r["type"]] = max(levels.get(r["type"], LOW), _level(r["severity"]))

    if any(lv == HIGH for lv in levels.values()):
        decision["overall_risk"] = "High"
        decision["rationale"].append("Rule 1: at least one risk factor is High")

    mediums = [f for f in PERFECT_STORM_FACTORS if levels.get(f, LOW) >= MEDIUM]
    if len(mediums) >= PERFECT_STORM_MIN_MEDIUMS:
        decision["overall_risk"] = "High"
        _add_flag(decision, "Perfect Storm")
        decision["rationale"].append(
            f"Rule 1 (Perfect Storm): {', '.join(sorted(mediums))} all >= Medium, upgraded to High"
        )
    elif any(lv == MEDIUM for lv in levels.values()):
        _raise_risk(decision, "Medium")


def rule_ai_insights(record, decision):
    """
    Rule 1b: act on the AI's structured insight codes.
      - CONFLICTING_DATA / OUTDATED_DATA / MISSING_DATA / NEEDS_HUMAN_REVIEW -> human review
      - POTENTIAL_DELAY: largest estimated delay >= 3 days -> Medium, >= 7 days -> High
      - EXTREME_EVENT rated High -> High risk
      - MULTIPLE_RISKS rated High -> High risk (Medium combos are Rule 1's job)
    """
    insights = record["insights"]
    for ins in insights:
        if ins["code"] in DATA_QUALITY_INSIGHTS:
            decision["needs_human"] = True
            _add_flag(decision, f"AI flagged: {ins['code']}")
            decision["rationale"].append(f"Rule 1b: {_describe_insight(ins)} -> human review")

    delays = [i for i in insights if i["code"] == "POTENTIAL_DELAY"]
    if delays:
        worst = max(delays, key=lambda i: i["estimated_delay_days"])
        days = worst["estimated_delay_days"]
        if days >= DELAY_DAYS_HIGH:
            _raise_risk(decision, "High")
        elif days >= DELAY_DAYS_LIMIT:
            _raise_risk(decision, "Medium")
        if days >= DELAY_DAYS_LIMIT:
            _add_flag(decision, "Significant Delay Expected")
            decision["rationale"].append(
                f"Rule 1b: {_describe_insight(worst)} -> risk {decision["overall_risk"]}"
            )

    for ins in insights:
        if ins["code"] in ("EXTREME_EVENT", "MULTIPLE_RISKS") and _level(ins["severity"]) == HIGH:
            _raise_risk(decision, "High")
            _add_flag(decision, "Extreme Event" if ins["code"] == "EXTREME_EVENT" else "Compound Risk")
            decision["rationale"].append(f"Rule 1b: {_describe_insight(ins)} -> risk High")


def rule_asset_reallocation(record, decision):
    """
    Rule 2: severe_crosswinds on a Light Freight vehicle -> reassign to Heavy Freight.
    """
    factor_types = {r["type"] for r in record["risk_factors"]}
    if CROSSWIND_FACTOR in factor_types or record["primary_risk_factor"] == CROSSWIND_FACTOR:
        if record["transport_type"] == "Light Freight":
            record["transport_type"] = "Heavy Freight"
            decision["actions"].append("Reassign load to a Heavy Freight carrier")
            _add_flag(decision, "Asset Reallocated")
            decision["rationale"].append(
                "Rule 2: severe_crosswinds + Light Freight -> Heavy Freight (rollover risk)"
            )
        else:
            decision["rationale"].append(
                f"Rule 2: severe_crosswinds noted, {record['transport_type']} already suitable"
            )


def rule_dynamic_insurance(record, decision):
    """
    Rule 4: piracy_threat or severe_civil_unrest -> update financial profile
    and hold until a human confirms extended insurance was bought.
    """
    factor_types = {r["type"] for r in record["risk_factors"]}
    triggered = INSURANCE_TRIGGERS & (factor_types | {record["primary_risk_factor"]})

    if triggered:
        decision["hold_shipment"] = True
        decision["needs_human"] = True
        _add_flag(decision, "Premium Increase Required")
        decision["actions"].append("Update financial profile: extended insurance needed")
        decision["rationale"].append(
            f"Rule 4: {', '.join(sorted(triggered))} detected, holding until insurance confirmed"
        )
        decision["overall_risk"] = "High"


def rule_low_risk_validation(record, decision, db_records, now):
    """
    Rule 3: never auto-approve a 'Low' route that recently failed.
    Ask the Data Manager for the last 21 days of saved records on this exact route.
    """
    if decision["overall_risk"] != "Low":
        return

    since = now - timedelta(days=HISTORY_WINDOW_DAYS)
    try:
        past = data_manager.get_route_history(db_records, record["route_id"], since)
    except (KeyError, TypeError, ValueError) as exc:
        decision["needs_human"] = True
        _add_flag(decision, "Route history unavailable")
        decision["rationale"].append(f"Rule 3: could not read route history ({exc}), needs human")
        return

    problem_runs = [p for p in past if p.get("flagged") or p.get("delayed")]
    if problem_runs:
        decision["needs_human"] = True
        decision["hold_shipment"] = True
        _add_flag(decision, "Cautionary Override")
        decision["actions"].append("Require human dispatcher sign-off")
        decision["rationale"].append(
            f"Rule 3: AI says Low but {len(problem_runs)} shipment(s) on route "
            f"{record['route_id']} were flagged or delayed in the last {HISTORY_WINDOW_DAYS} days"
        )
    else:
        decision["rationale"].append("Rule 3: Low risk and clean 21-day history, auto-approve")


def rule_inventory_replacement(record, decision):
    """
    Rule 5: cargo likely destroyed by a sudden extreme event at the origin port
    (e.g. typhoon at CNSHA) -> Procurement Alert.
    Do not just stop the shipment: tell the company to reorder now.
    """
    event = record.get("extreme_event") or NO_EXTREME_EVENT
    at_origin = record["affected_location"] == record["origin_port"]

    if (record["expected_impact"] in CARGO_DESTRUCTION_IMPACTS
            and event != NO_EXTREME_EVENT and at_origin):
        goods = record["goods"].get("description", "the goods on this shipment")
        decision["hold_shipment"] = True
        _add_flag(decision, "Procurement Alert")
        decision["actions"].append(f"Reorder goods immediately: {goods} (extreme event: {event})")
        _add_alert(
            decision, "procurement_team", ["email", "sms"],
            f"Shipment {record['shipment_id']} is at risk of destruction ({event} at "
            f"{record['origin']}). Consider reordering to avoid stock-out.",
        )
        decision["rationale"].append(
            f"Rule 5: Cargo Destruction + extreme_event={event} @{record['origin_port']} (origin)"
        )


def decide_outcome(record, decision):
    """Turn the accumulated flags into one final operational outcome."""
    if decision["outcome"] == "REJECT":
        return

    goods = record["goods"]
    time_sensitive = goods.get("perishable") or goods.get("time_sensitive")
    alternative = record.get("alternative_route")

    if "Procurement Alert" in decision["flags"]:
        decision["outcome"] = "DELAY"
    elif "Premium Increase Required" in decision["flags"]:
        decision["outcome"] = "INSURE"
    elif decision["overall_risk"] == "High":
        # Prefer rerouting for time-sensitive cargo, otherwise delay the departure
        if time_sensitive and alternative and alternative.get("name"):
            decision["outcome"] = "REROUTE"
            decision["actions"].append(f"Reroute via {alternative['name']}")
        else:
            decision["outcome"] = "DELAY"
            decision["actions"].append("Delay departure until conditions clear")
        decision["needs_human"] = True
    elif decision["overall_risk"] == "Medium":
        decision["outcome"] = "PROCEED"
        decision["actions"].append("Proceed with monitoring")
    else:
        decision["outcome"] = "PROCEED"

    # Anything held for a human is not fully automatic
    if decision["hold_shipment"] and decision["outcome"] == "PROCEED":
        decision["outcome"] = "ESCALATE"


# --------------------------------------------------------------------------
# PART 3: ESCALATION PROTOCOLS
# --------------------------------------------------------------------------
def check_financial_threshold(record, decision):
    """
    If an automated reroute adds more than 20% distance, stop the auto-reroute
    and send an 'Excessive Cost' alert to the Operations Director.
    """
    if decision["outcome"] != "REROUTE":
        return

    base = record.get("baseline_distance_km")
    new = (record.get("alternative_route") or {}).get("distance_km")
    if not base or not new:
        decision["needs_human"] = True
        _add_flag(decision, "Reroute distance unknown")
        decision["rationale"].append("Financial check: cannot compare distances, needs human")
        return

    increase_pct = (new - base) / base * 100
    if increase_pct > REROUTE_COST_LIMIT_PCT:
        decision["outcome"] = "ESCALATE"
        decision["hold_shipment"] = True
        decision["needs_human"] = True
        _add_flag(decision, "Excessive Cost")
        decision["actions"] = [a for a in decision["actions"] if not a.startswith("Reroute")]
        decision["actions"].append("Automatic rerouting stopped")
        _add_alert(
            decision, "operations_director", ["email"],
            f"Excessive Cost: reroute for {record['shipment_id']} adds "
            f"{increase_pct:.1f}% distance (limit {REROUTE_COST_LIMIT_PCT:.0f}%).",
        )
        decision["rationale"].append(
            f"Financial check: reroute +{increase_pct:.1f}% > {REROUTE_COST_LIMIT_PCT:.0f}%, stopped"
        )
    else:
        decision["rationale"].append(
            f"Financial check: reroute +{increase_pct:.1f}% is within the limit"
        )


def stakeholder_alerting(record, decision):
    """
    Stakeholder Alerting: a High risk shipment sends an urgent SMS and email
    to the cargo owner and the active supply chain manager, including the
    AI's risk factors and insight flags. The message text is built here from
    the AI's codes; the AI itself never writes sentences.
    """
    if decision["overall_risk"] != "High":
        return

    factors = "; ".join(
        f"{f['type']}/{f['severity']} @{_port_name(f.get('location', 'Route'))}"
        f" ({f.get('detail', '-')})"
        for f in record["risk_factors"][:3]
    ) or "none listed"
    flags = "; ".join(_describe_insight(i) for i in record["insights"][:3]) or "none"
    summary = (
        f"URGENT: shipment {record['shipment_id']} ({record['origin']} -> "
        f"{record['destination']}) is HIGH RISK. "
        f"Main risk: {record['primary_risk_factor']} at {_port_name(record['affected_location'])}. "
        f"Expected impact: {record['expected_impact']}. "
        f"Recommended: {decision["outcome"]}. "
        f"Risk factors: {factors}. AI flags: {flags}."
    )
    for recipient in ("cargo_owner", "supply_chain_manager"):
        _add_alert(decision, recipient, ["sms", "email"], summary)


def escalation_protocol(decision):
    """Final gate: anything needing a human is never marked as fully automatic."""
    if decision["needs_human"] and decision["outcome"] == "PROCEED":
        decision["outcome"] = "ESCALATE"
    if decision["needs_human"]:
        decision["actions"].append("Route to human review queue")


# --------------------------------------------------------------------------
# MAIN ENTRY POINTS
# --------------------------------------------------------------------------
def evaluate_shipment(ai_record, db_records, now=None):
    """
    Run one AI Manager row through every rule.

    ai_record  - one row of ai_manager.assess_shipments() as a dict
    db_records - list from data_manager.load_records(data_manager.DB_FILE)

    Returns (record, decision): the prepared record (with route_id, origin,
    destination, ...) and its decision dict, ready for
    data_manager.add_record(file, db_records, record, decision_to_dict(decision)).
    """
    now = now or datetime.now()
    record = prepare_record(ai_record)  # copy, never mutates the caller's data
    decision = new_decision(str(record.get("shipment_id", "UNKNOWN")))

    # Part 1
    if not validate_record(record, decision, now):
        record.pop("_dropped_items", None)
        return record, decision

    # Part 2 (risk-raising rules run before Rule 3, which only checks "Low" shipments)
    rule_perfect_storm(record, decision)
    rule_ai_insights(record, decision)
    rule_asset_reallocation(record, decision)
    rule_dynamic_insurance(record, decision)
    rule_low_risk_validation(record, decision, db_records, now)
    rule_inventory_replacement(record, decision)
    decide_outcome(record, decision)

    # Part 3
    check_financial_threshold(record, decision)
    stakeholder_alerting(record, decision)
    escalation_protocol(decision)

    record.pop("_dropped_items", None)  # internal only, not saved
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
        "sources": ["open_meteo_weather", "gdelt_news"], "conflicting_sources": False,
        "extreme_event": "none", "insights": [], "alternative_route": None,
        "external_data_fetched_at": (now - timedelta(hours=1)).isoformat(),
    }

    def factor(t, sev, loc="Route", src="open_meteo_weather", ind="-"):
        return {"type": t, "severity": sev, "location": loc, "source": src, "detail": ind}

    def insight(code, rt, sev, loc="Route", days=0):
        return {"code": code, "risk_type": rt, "severity": sev, "location": loc,
                "estimated_delay_days": days}

    cases = {
        "Perfect Storm (perishable, reroute too long)": {
            **base,
            "risk_factors": [
                factor("weather", "Medium", "Strait of Malacca", ind="wind_gust_kmh=55"),
                factor("port_congestion", "Medium", "NLRTM", "gdelt_news", "news_articles=3"),
                factor("labor_shortage", "Medium", "NLRTM", "gdelt_news", "news_articles=2"),
            ],
            "goods": {"description": "Fresh fruit", "perishable": True},
            "alternative_route": {"name": "Cape of Good Hope", "distance_km": 20000},
        },
        "Piracy": {
            **base, "shipment_id": "SHP-002", "primary_risk_factor": "piracy_threat",
            "affected_location": "Singapore Strait",
            "risk_factors": [factor("piracy_threat", "High", "Singapore Strait",
                                    "gdelt_news", "news_articles=4")],
        },
        "Low risk but bad history": {
            **base, "shipment_id": "SHP-003",
            "risk_factors": [factor("weather", "Low", ind="wind_gust_kmh=20")],
        },
        "Typhoon destroys cargo at origin": {
            **base, "shipment_id": "SHP-004", "origin_port": "CNSHA", "destination_port": "SGSIN",
            "affected_location": "CNSHA", "expected_impact": "Cargo Destruction",
            "extreme_event": "typhoon",
            "risk_factors": [factor("weather", "High", "CNSHA", ind="wind_gust_kmh=180")],
            "insights": [insight("EXTREME_EVENT", "weather", "High", "CNSHA", 10),
                         insight("OUTDATED_DATA", "none", "Low")],
        },
        "AI fallback response": {
            **base, "shipment_id": "SHP-005", "risk_factors": [], "sources": [],
            "confidence_score": 0.0, "conflicting_sources": True,
            "primary_risk_factor": "infrastructure_disruption", "affected_location": "Unknown",
            "expected_impact": "None",
            "insights": [insight("MISSING_DATA", "none", "High")],
        },
        "AI returned free text": {
            **base, "shipment_id": "SHP-006", "affected_location": "near Shanghai port",
            "risk_factors": [factor("weather", "Low")],
            "insights": ["Typhoon may cause delays."],
        },
        "Bad AI record": {"shipment_id": "SHP-007"},
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
        print("Outcome :", d["outcome"], "| Risk:", d["overall_risk"], "| Human:", d["needs_human"])
        print("Flags   :", d["flags"])
        print("Actions :", d["actions"])
        print("Alerts  :", [(a["recipient"], a["channels"]) for a in d["alerts"]])
        for line in d["rationale"]:
            print("  -", line)