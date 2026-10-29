from datetime import datetime, timedelta
import data_manager
import validator
from config import (ALLOWED_IMPACT, ALLOWED_LOCATIONS, ALLOWED_RISK_TYPES,
                        ALLOWED_SEVERITY, INSIGHT_CODES, INSIGHT_RISK_TYPES)

# Thresholds and rule inputs (change them here, not inside the rules)
LOW, MEDIUM, HIGH = 1, 2, 3
LEVEL_FROM_TEXT = {"low": LOW, "medium": MEDIUM, "high": HIGH}
CONFIDENCE_MIN, HISTORY_WINDOW_DAYS, PERFECT_STORM_MIN_MEDIUMS = 0.60, 21, 3
DATA_MAX_AGE_HOURS, DELAY_DAYS_LIMIT, DELAY_DAYS_HIGH = 24, 3, 7
PERFECT_STORM_FACTORS = {"weather", "port_congestion", "labor_shortage"}
INSURANCE_TRIGGERS = {"piracy_threat", "severe_civil_unrest"}
CARGO_DESTRUCTION_IMPACTS = {"Cargo Destruction"}
DATA_QUALITY_INSIGHTS = {"CONFLICTING_DATA", "OUTDATED_DATA", "MISSING_DATA", "NEEDS_HUMAN_REVIEW"}
REQUIRED_FIELDS = ["shipment_id", "origin_port", "destination_port", "risk_factors", "primary_risk_factor",
                   "affected_location", "expected_impact", "confidence_score", "sources"]
INSIGHT_KEYS = ("code", "risk_type", "severity", "location", "estimated_delay_days")

def new_decision(shipment_id):
    """Fresh decision dict. outcome: PROCEED / DELAY / INSURE / ESCALATE / REJECT."""
    return {"shipment_id": shipment_id, "overall_risk": "Low", "outcome": "PROCEED", "hold_shipment": False,
            "needs_human": False, "flags": [], "actions": [], "alerts": [], "rationale": []}

def _level(text):
    return LEVEL_FROM_TEXT.get(str(text).strip().lower(), LOW)

def _note(d, why, flag=None, action=None, human=False):
    """Record why a rule fired, plus an optional flag (no duplicates), action and human-review request."""
    if human:
        d["needs_human"] = True
    if flag and flag not in d["flags"]:
        d["flags"].append(flag)
    if action:
        d["actions"].append(action)
    d["rationale"].append(why)

def _raise_risk(d, level):
    if _level(level) > _level(d["overall_risk"]):
        d["overall_risk"] = level

def _describe(i):
    """e.g. 'POTENTIAL_DELAY weather/High @CNSHA +8d'."""
    days = f" +{i['estimated_delay_days']}d" if i["estimated_delay_days"] else ""
    return f"{i['code']} {i['risk_type']}/{i['severity']} @{i['location']}{days}"

def _clean_list(value, keys):
    """Keep dict items that have every key; also return how many were dropped."""
    good = [i for i in value if isinstance(i, dict) and all(k in i for k in keys)] if isinstance(value, list) else []
    return good, len(value) - len(good) if isinstance(value, list) else 0

def prepare_record(ai_record):
    """Copy the AI row and add route_id, port names, defaults and cleaned lists."""
    r = dict(ai_record)
    o, dst = r.get("origin_port", ""), r.get("destination_port", "")
    r.setdefault("route_id", f"{o}-{dst}")
    for key, code in (("origin", o), ("destination", dst)):
        r.setdefault(key, validator.PORTS_BY_CODE[code]["name"] if code in validator.PORTS_BY_CODE else str(code))
    for key, kind, default in (("sources", list, []),):
        if not isinstance(r.get(key), kind):
            r[key] = default
    r["risk_factors"], bad_f = _clean_list(r.get("risk_factors"), ("type", "severity"))
    r["insights"], bad_i = _clean_list(r.get("insights"), INSIGHT_KEYS)
    for ins in r["insights"]:
        try:
            ins["estimated_delay_days"] = max(0, int(ins["estimated_delay_days"]))
        except (TypeError, ValueError):
            ins["estimated_delay_days"] = 0
    r["_dropped_items"] = bad_f + bad_i
    return r

def validate_record(r, d, now):
    """Return False (REJECT) for unusable records; flag softer problems for human review."""
    missing = [f for f in REQUIRED_FIELDS if r.get(f) in (None, "")]
    conf = r.get("confidence_score")
    if missing or isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
        d["outcome"] = "REJECT"
        if missing:
            _note(d, f"Validation failed: missing fields {missing}", "Incomplete AI record", human=True)
        else:
            _note(d, "Validation failed: confidence_score not in 0-1", "Invalid confidence score", human=True)
        return False
    checks = [("primary_risk_factor", r.get("primary_risk_factor"), ALLOWED_RISK_TYPES),
              ("affected_location", r.get("affected_location"), ALLOWED_LOCATIONS),
              ("expected_impact", r.get("expected_impact"), ALLOWED_IMPACT)]
    for f in r["risk_factors"]:
        checks += [("risk_factors.type", f["type"], ALLOWED_RISK_TYPES),
                   ("risk_factors.severity", f["severity"], ALLOWED_SEVERITY)]
    for i in r["insights"]:
        checks += [("insights.code", i["code"], INSIGHT_CODES), ("insights.risk_type", i["risk_type"],
                   INSIGHT_RISK_TYPES), ("insights.severity", i["severity"], ALLOWED_SEVERITY)]
    problems = [f"{n}={v!r}" for n, v, allowed in checks if v not in allowed]
    problems += [f"{r['_dropped_items']} malformed list item(s) dropped"] if r["_dropped_items"] else []
    try:
        fetched = datetime.fromisoformat(str(r.get("external_data_fetched_at")))
    except ValueError:
        fetched = None  # missing or unreadable timestamp: skip the age check
    for failed, flag, why in (
            (problems, "AI output outside schema", f"Validation: unexpected AI values {problems}"),
            (conf < CONFIDENCE_MIN, "Low AI confidence", f"Confidence {conf:.2f} is below {CONFIDENCE_MIN:.2f}"),
            (fetched and now - fetched > timedelta(hours=DATA_MAX_AGE_HOURS), "Outdated external data",
             f"External data is older than {DATA_MAX_AGE_HOURS}h"),
            (r.get("conflicting_sources") is True, "Conflicting sources",
             "AI reported conflicting or missing information")):
        if failed:
            _note(d, why, flag, human=True)
    return True

def rule_perfect_storm(r, d):
    """Rule 1: any High factor -> High; 3 Medium weather/congestion/labor factors -> High."""
    levels = {}
    for f in r["risk_factors"]:
        levels[f["type"]] = max(levels.get(f["type"], LOW), _level(f["severity"]))
    if HIGH in levels.values():
        d["overall_risk"] = "High"
        _note(d, "Rule 1: at least one risk factor is High")
    mediums = [f for f in PERFECT_STORM_FACTORS if levels.get(f, LOW) >= MEDIUM]
    if len(mediums) >= PERFECT_STORM_MIN_MEDIUMS:
        d["overall_risk"] = "High"
        _note(d, f"Rule 1 (Perfect Storm): {', '.join(sorted(mediums))} all >= Medium, upgraded to High",
              "Perfect Storm")
    elif MEDIUM in levels.values():
        _raise_risk(d, "Medium")

def rule_ai_insights(r, d):
    """Rule 1b: data-quality codes -> human; delay >=3d Medium, >=7d High; High MULTIPLE_RISKS -> High."""
    for i in r["insights"]:
        if i["code"] in DATA_QUALITY_INSIGHTS:
            _note(d, f"Rule 1b: {_describe(i)} -> human review", f"AI flagged: {i['code']}", human=True)
    delays = [i for i in r["insights"] if i["code"] == "POTENTIAL_DELAY"]
    worst = max(delays, key=lambda i: i["estimated_delay_days"]) if delays else None
    if worst and worst["estimated_delay_days"] >= DELAY_DAYS_LIMIT:
        _raise_risk(d, "High" if worst["estimated_delay_days"] >= DELAY_DAYS_HIGH else "Medium")
        _note(d, f"Rule 1b: {_describe(worst)} -> risk {d['overall_risk']}", "Significant Delay Expected")
    for i in r["insights"]:
        if i["code"] == "MULTIPLE_RISKS" and _level(i["severity"]) == HIGH:
            _raise_risk(d, "High")
            _note(d, f"Rule 1b: {_describe(i)} -> risk High", "Compound Risk")

def rule_dynamic_insurance(r, d):
    """Rule 4: piracy_threat / severe_civil_unrest -> hold until extended insurance is confirmed."""
    triggered = INSURANCE_TRIGGERS & ({f["type"] for f in r["risk_factors"]} | {r["primary_risk_factor"]})
    if triggered:
        d["hold_shipment"], d["overall_risk"] = True, "High"
        _note(d, f"Rule 4: {', '.join(sorted(triggered))} detected, holding until insurance confirmed",
              "Premium Increase Required", "Update financial profile: extended insurance needed", human=True)

def rule_low_risk_validation(r, d, Data_Manager, now):
    """Rule 3: a 'Low' route flagged or delayed in the last 21 days needs dispatcher sign-off."""
    if d["overall_risk"] != "Low":
        return
    try:

        search_filter = {
            "route_id" : r["route_id"],
            "saved_at" : now - timedelta(days=HISTORY_WINDOW_DAYS),
            "operator" : ">="
        }
        past = Data_Manager.get_route_history(search_filter)
    except (KeyError, TypeError, ValueError) as exc:
        return _note(d, f"Rule 3: could not read route history ({exc}), needs human",
                     "Route history unavailable", human=True)
    problems = [p for p in past if p.get("flagged") or p.get("delayed")]
    if not problems:
        return _note(d, "Rule 3: Low risk and clean 21-day history, auto-approve")
    d["hold_shipment"] = True
    _note(d, f"Rule 3: AI says Low but {len(problems)} shipment(s) on route {r['route_id']} were flagged or "
          f"delayed in the last {HISTORY_WINDOW_DAYS} days", "Cautionary Override",
          "Require human dispatcher sign-off", human=True)

def rule_inventory_replacement(r, d):
    """Rule 5: Cargo Destruction predicted at the origin port -> Procurement Alert to reorder the goods."""
    if r["expected_impact"] in CARGO_DESTRUCTION_IMPACTS and r["affected_location"] == r["origin_port"]:
        d["hold_shipment"] = True
        d["alerts"].append({"recipient": "procurement_team", "channels": ["email", "sms"], "message":
                            f"Shipment {r['shipment_id']} is at risk of destruction at {r['origin']}. "
                            "Consider reordering to avoid stock-out."})
        _note(d, f"Rule 5: Cargo Destruction @{r['origin_port']} (origin)", "Procurement Alert",
              "Reorder goods immediately: the goods on this shipment")

def decide_outcome(d):
    """Turn the flags into one outcome: Procurement Alert or High risk -> DELAY, insurance -> INSURE."""
    if "Procurement Alert" in d["flags"]:
        d["outcome"] = "DELAY"
    elif "Premium Increase Required" in d["flags"]:
        d["outcome"] = "INSURE"
    elif d["overall_risk"] == "High":
        d["outcome"] = "DELAY"
        d["actions"].append("Delay departure until conditions clear")
        d["needs_human"] = True
    else:
        d["outcome"] = "PROCEED"
        if d["overall_risk"] == "Medium":
            d["actions"].append("Proceed with monitoring")
    if d["hold_shipment"] and d["outcome"] == "PROCEED":
        d["outcome"] = "ESCALATE"

def evaluate_shipment(ai_record, Data_Manager, now=None):
    """Run one AI row through every rule. Returns (prepared record, decision dict)."""
    now = now or datetime.now()
    r = prepare_record(ai_record)
    d = new_decision(str(r.get("shipment_id", "UNKNOWN")))
    if validate_record(r, d, now):
        for rule in (rule_perfect_storm, rule_ai_insights, rule_dynamic_insurance):
            rule(r, d)
        rule_low_risk_validation(r, d, Data_Manager, now)  # after the risk-raising rules: only checks "Low"
        rule_inventory_replacement(r, d)
        decide_outcome(d)
        if d["needs_human"]:  # final gate: anything needing a human is never fully automatic
            d["outcome"] = "ESCALATE" if d["outcome"] == "PROCEED" else d["outcome"]
            d["actions"].append("Route to human review queue")
    r.pop("_dropped_items", None)
    return r, d

def evaluate_shipments(assessments, Data_Manager, now=None):
    """Evaluate every row of ai_manager.assess_shipments(); returns [(record, decision), ...]."""
    results = []
    for row in assessments.to_dict("records"):
        try:
            results.append(evaluate_shipment(row, Data_Manager, now))
        except Exception as exc:
            d = new_decision(str(row.get("shipment_id", "UNKNOWN")))
            d["outcome"] = "REJECT"
            _note(d, f"Evaluation failed: {exc!r}", "Evaluation error", human=True)
            results.append((row, d))
    return results