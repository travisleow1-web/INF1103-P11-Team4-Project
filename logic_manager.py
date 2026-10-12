"""logic_manager.py - business rules for the Logistics Risk Assessment System (Singapore).

Takes one row of ai_manager.assess_shipments() plus saved records from data_manager,
runs the rules and returns (record, decision dict). The AI never makes the final decision.
Allowed AI values are imported from ai_manager so both managers share the same fields.
Run this file directly for an offline test with sample AI responses (no API calls).
"""
import copy
import math
from datetime import datetime, timedelta

import data_manager
import validator
from ai_manager import (ALLOWED_EXTREME_EVENTS, ALLOWED_IMPACT, ALLOWED_LOCATIONS, ALLOWED_RISK_TYPES,
                        ALLOWED_SEVERITY, INSIGHT_CODES, INSIGHT_RISK_TYPES)

# Thresholds and rule inputs (change them here, not inside the rules)
LOW, MEDIUM, HIGH = 1, 2, 3
LEVEL_FROM_TEXT = {"low": LOW, "medium": MEDIUM, "high": HIGH}
CONFIDENCE_MIN, HISTORY_WINDOW_DAYS, PERFECT_STORM_MIN_MEDIUMS = 0.60, 21, 3
REROUTE_COST_LIMIT_PCT, DATA_MAX_AGE_HOURS, DELAY_DAYS_LIMIT, DELAY_DAYS_HIGH = 20.0, 24, 3, 7
PERFECT_STORM_FACTORS = {"weather", "port_congestion", "labor_shortage"}
INSURANCE_TRIGGERS = {"piracy_threat", "severe_civil_unrest"}
CROSSWIND_FACTOR, NO_EXTREME_EVENT, DEFAULT_TRANSPORT_TYPE = "severe_crosswinds", "none", "Cargo Vessel"
CARGO_DESTRUCTION_IMPACTS = {"Cargo Destruction"}
DATA_QUALITY_INSIGHTS = {"CONFLICTING_DATA", "OUTDATED_DATA", "MISSING_DATA", "NEEDS_HUMAN_REVIEW"}
REQUIRED_FIELDS = ["shipment_id", "origin_port", "destination_port", "risk_factors", "primary_risk_factor",
                   "affected_location", "expected_impact", "confidence_score", "sources"]
INSIGHT_KEYS = ("code", "risk_type", "severity", "location", "estimated_delay_days")


def new_decision(shipment_id):
    """Fresh decision dict. outcome: PROCEED / DELAY / REROUTE / INSURE / ESCALATE / REJECT."""
    return {"shipment_id": shipment_id, "overall_risk": "Low", "outcome": "PROCEED", "hold_shipment": False,
            "needs_human": False, "flags": [], "actions": [], "alerts": [], "rationale": []}


def decision_to_dict(decision):
    """Independent copy of a decision, in the shape data_manager.add_record expects."""
    return copy.deepcopy(decision)


# ---------------- Helpers ----------------
def _level(text):
    return LEVEL_FROM_TEXT.get(str(text).strip().lower(), LOW)


def _add_flag(d, flag):
    if flag not in d["flags"]:
        d["flags"].append(flag)


def _human(d, flag, why):
    """Send to human review with a flag and a reason."""
    d["needs_human"] = True
    _add_flag(d, flag)
    d["rationale"].append(why)


def _raise_risk(d, level):
    if _level(level) > _level(d["overall_risk"]):
        d["overall_risk"] = level


def _port_name(code):
    port = validator.PORTS_BY_CODE.get(code)
    return port["name"] if port else str(code)


def _describe(i):
    """e.g. 'POTENTIAL_DELAY weather/High @CNSHA +8d'."""
    days = f" +{i['estimated_delay_days']}d" if i["estimated_delay_days"] else ""
    return f"{i['code']} {i['risk_type']}/{i['severity']} @{i['location']}{days}"


def _clean_list(value, keys):
    """Keep dict items that have every key; also return how many were dropped."""
    if not isinstance(value, list):
        return [], 0
    good = [i for i in value if isinstance(i, dict) and all(k in i for k in keys)]
    return good, len(value) - len(good)


# ---------------- Part 0: prepare the AI row ----------------
def prepare_record(ai_record):
    """Copy of the AI row plus route_id, port names, defaults and cleaned lists."""
    r = dict(ai_record)
    o, dst = r.get("origin_port", ""), r.get("destination_port", "")
    r.setdefault("route_id", f"{o}-{dst}")
    r.setdefault("origin", _port_name(o))
    r.setdefault("destination", _port_name(dst))
    r.setdefault("transport_type", DEFAULT_TRANSPORT_TYPE)
    for key, kind, default in (("goods", dict, {}), ("alternative_route", dict, None), ("sources", list, [])):
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
    if not r.get("baseline_distance_km"):  # straight-line (haversine) distance in km
        try:
            la1, lo1, la2, lo2 = (math.radians(float(r[k])) for k in
                                  ("origin_lat", "origin_lon", "destination_lat", "destination_lon"))
            a = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
            r["baseline_distance_km"] = round(2 * 6371.0 * math.asin(math.sqrt(a)), 1)
        except (KeyError, TypeError, ValueError):
            r["baseline_distance_km"] = None
    return r


# ---------------- Part 1: validation ----------------
def validate_record(r, d, now):
    """Return False (REJECT) for unusable records; flag softer problems for human review."""
    missing = [f for f in REQUIRED_FIELDS if r.get(f) in (None, "")]
    conf = r.get("confidence_score")
    if missing or isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
        d["outcome"] = "REJECT"
        if missing:
            _human(d, "Incomplete AI record", f"Validation failed: missing fields {missing}")
        else:
            _human(d, "Invalid confidence score", "Validation failed: confidence_score not in 0-1")
        return False

    checks = [("primary_risk_factor", r.get("primary_risk_factor"), ALLOWED_RISK_TYPES),
              ("affected_location", r.get("affected_location"), ALLOWED_LOCATIONS),
              ("expected_impact", r.get("expected_impact"), ALLOWED_IMPACT),
              ("extreme_event", r.get("extreme_event", NO_EXTREME_EVENT), ALLOWED_EXTREME_EVENTS)]
    for f in r["risk_factors"]:
        checks += [("risk_factors.type", f["type"], ALLOWED_RISK_TYPES),
                   ("risk_factors.severity", f["severity"], ALLOWED_SEVERITY)]
    for i in r["insights"]:
        checks += [("insights.code", i["code"], INSIGHT_CODES), ("insights.risk_type", i["risk_type"],
                   INSIGHT_RISK_TYPES), ("insights.severity", i["severity"], ALLOWED_SEVERITY)]
    problems = [f"{n}={v!r}" for n, v, allowed in checks if v not in allowed]
    if r["_dropped_items"]:
        problems.append(f"{r['_dropped_items']} malformed list item(s) dropped")
    if problems:
        _human(d, "AI output outside schema", f"Validation: unexpected AI values {problems}")
    if conf < CONFIDENCE_MIN:
        _human(d, "Low AI confidence", f"Confidence {conf:.2f} is below {CONFIDENCE_MIN:.2f}")
    try:
        fetched = datetime.fromisoformat(str(r.get("external_data_fetched_at")))
    except ValueError:
        fetched = None  # missing or unreadable timestamp: skip the age check
    if fetched and now - fetched > timedelta(hours=DATA_MAX_AGE_HOURS):
        _human(d, "Outdated external data", f"External data is older than {DATA_MAX_AGE_HOURS}h")
    if r.get("conflicting_sources") is True:
        _human(d, "Conflicting sources", "AI reported conflicting or missing information")
    return True


# ---------------- Part 2: operational rules ----------------
def rule_perfect_storm(r, d):
    """Rule 1: any High factor -> High; 3 Medium weather/congestion/labor factors -> High."""
    levels = {}
    for f in r["risk_factors"]:
        levels[f["type"]] = max(levels.get(f["type"], LOW), _level(f["severity"]))
    if HIGH in levels.values():
        d["overall_risk"] = "High"
        d["rationale"].append("Rule 1: at least one risk factor is High")
    mediums = [f for f in PERFECT_STORM_FACTORS if levels.get(f, LOW) >= MEDIUM]
    if len(mediums) >= PERFECT_STORM_MIN_MEDIUMS:
        d["overall_risk"] = "High"
        _add_flag(d, "Perfect Storm")
        d["rationale"].append(f"Rule 1 (Perfect Storm): {', '.join(sorted(mediums))} all >= Medium, upgraded to High")
    elif MEDIUM in levels.values():
        _raise_risk(d, "Medium")


def rule_ai_insights(r, d):
    """Rule 1b: data-quality codes -> human; delay >=3d Medium, >=7d High; High EXTREME_EVENT/MULTIPLE_RISKS -> High."""
    for i in r["insights"]:
        if i["code"] in DATA_QUALITY_INSIGHTS:
            _human(d, f"AI flagged: {i['code']}", f"Rule 1b: {_describe(i)} -> human review")
    delays = [i for i in r["insights"] if i["code"] == "POTENTIAL_DELAY"]
    if delays:
        worst = max(delays, key=lambda i: i["estimated_delay_days"])
        if worst["estimated_delay_days"] >= DELAY_DAYS_LIMIT:
            _raise_risk(d, "High" if worst["estimated_delay_days"] >= DELAY_DAYS_HIGH else "Medium")
            _add_flag(d, "Significant Delay Expected")
            d["rationale"].append(f"Rule 1b: {_describe(worst)} -> risk {d['overall_risk']}")
    for i in r["insights"]:
        if i["code"] in ("EXTREME_EVENT", "MULTIPLE_RISKS") and _level(i["severity"]) == HIGH:
            _raise_risk(d, "High")
            _add_flag(d, "Extreme Event" if i["code"] == "EXTREME_EVENT" else "Compound Risk")
            d["rationale"].append(f"Rule 1b: {_describe(i)} -> risk High")


def rule_asset_reallocation(r, d):
    """Rule 2: severe_crosswinds on Light Freight -> reassign to Heavy Freight."""
    if CROSSWIND_FACTOR not in {f["type"] for f in r["risk_factors"]} | {r["primary_risk_factor"]}:
        return
    if r["transport_type"] == "Light Freight":
        r["transport_type"] = "Heavy Freight"
        d["actions"].append("Reassign load to a Heavy Freight carrier")
        _add_flag(d, "Asset Reallocated")
        d["rationale"].append("Rule 2: severe_crosswinds + Light Freight -> Heavy Freight (rollover risk)")
    else:
        d["rationale"].append(f"Rule 2: severe_crosswinds noted, {r['transport_type']} already suitable")


def rule_dynamic_insurance(r, d):
    """Rule 4: piracy_threat / severe_civil_unrest -> hold until extended insurance is confirmed."""
    triggered = INSURANCE_TRIGGERS & ({f["type"] for f in r["risk_factors"]} | {r["primary_risk_factor"]})
    if triggered:
        d["hold_shipment"] = d["needs_human"] = True
        _add_flag(d, "Premium Increase Required")
        d["actions"].append("Update financial profile: extended insurance needed")
        d["rationale"].append(f"Rule 4: {', '.join(sorted(triggered))} detected, holding until insurance confirmed")
        d["overall_risk"] = "High"


def rule_low_risk_validation(r, d, db_records, now):
    """Rule 3: a 'Low' route flagged or delayed in the last 21 days needs dispatcher sign-off."""
    if d["overall_risk"] != "Low":
        return
    try:
        past = data_manager.get_route_history(db_records, r["route_id"], now - timedelta(days=HISTORY_WINDOW_DAYS))
    except (KeyError, TypeError, ValueError) as exc:
        _human(d, "Route history unavailable", f"Rule 3: could not read route history ({exc}), needs human")
        return
    problems = [p for p in past if p.get("flagged") or p.get("delayed")]
    if not problems:
        d["rationale"].append("Rule 3: Low risk and clean 21-day history, auto-approve")
        return
    d["hold_shipment"] = True
    _human(d, "Cautionary Override", f"Rule 3: AI says Low but {len(problems)} shipment(s) on route "
           f"{r['route_id']} were flagged or delayed in the last {HISTORY_WINDOW_DAYS} days")
    d["actions"].append("Require human dispatcher sign-off")


def rule_inventory_replacement(r, d):
    """Rule 5: Cargo Destruction from an extreme event at the origin port -> Procurement Alert."""
    event = r.get("extreme_event") or NO_EXTREME_EVENT
    if (r["expected_impact"] in CARGO_DESTRUCTION_IMPACTS and event != NO_EXTREME_EVENT
            and r["affected_location"] == r["origin_port"]):
        d["hold_shipment"] = True
        _add_flag(d, "Procurement Alert")
        d["actions"].append(f"Reorder goods immediately: {r['goods'].get('description', 'the goods on this shipment')}"
                            f" (extreme event: {event})")
        d["alerts"].append({"recipient": "procurement_team", "channels": ["email", "sms"], "message":
                            f"Shipment {r['shipment_id']} is at risk of destruction ({event} at {r['origin']}). "
                            "Consider reordering to avoid stock-out."})
        d["rationale"].append(f"Rule 5: Cargo Destruction + extreme_event={event} @{r['origin_port']} (origin)")


def decide_outcome(r, d):
    """Turn the flags into one outcome; High risk reroutes time-sensitive cargo, else delays."""
    alt = r.get("alternative_route")
    if "Procurement Alert" in d["flags"]:
        d["outcome"] = "DELAY"
    elif "Premium Increase Required" in d["flags"]:
        d["outcome"] = "INSURE"
    elif d["overall_risk"] == "High":
        if (r["goods"].get("perishable") or r["goods"].get("time_sensitive")) and alt and alt.get("name"):
            d["outcome"] = "REROUTE"
            d["actions"].append(f"Reroute via {alt['name']}")
        else:
            d["outcome"] = "DELAY"
            d["actions"].append("Delay departure until conditions clear")
        d["needs_human"] = True
    else:
        d["outcome"] = "PROCEED"
        if d["overall_risk"] == "Medium":
            d["actions"].append("Proceed with monitoring")
    if d["hold_shipment"] and d["outcome"] == "PROCEED":
        d["outcome"] = "ESCALATE"


# ---------------- Part 3: escalation ----------------
def check_financial_threshold(r, d):
    """A reroute adding more than 20% distance is stopped and the Operations Director is alerted."""
    if d["outcome"] != "REROUTE":
        return
    base, new = r.get("baseline_distance_km"), (r.get("alternative_route") or {}).get("distance_km")
    if not base or not new:
        _human(d, "Reroute distance unknown", "Financial check: cannot compare distances, needs human")
        return
    pct = (new - base) / base * 100
    if pct <= REROUTE_COST_LIMIT_PCT:
        d["rationale"].append(f"Financial check: reroute +{pct:.1f}% is within the limit")
        return
    d["outcome"], d["hold_shipment"], d["needs_human"] = "ESCALATE", True, True
    _add_flag(d, "Excessive Cost")
    d["actions"] = [a for a in d["actions"] if not a.startswith("Reroute")] + ["Automatic rerouting stopped"]
    d["alerts"].append({"recipient": "operations_director", "channels": ["email"], "message":
                        f"Excessive Cost: reroute for {r['shipment_id']} adds {pct:.1f}% distance "
                        f"(limit {REROUTE_COST_LIMIT_PCT:.0f}%)."})
    d["rationale"].append(f"Financial check: reroute +{pct:.1f}% > {REROUTE_COST_LIMIT_PCT:.0f}%, stopped")


# ---------------- Entry points ----------------
def evaluate_shipment(ai_record, db_records, now=None):
    """Run one AI row through every rule. Returns (prepared record, decision dict)."""
    now = now or datetime.now()
    r = prepare_record(ai_record)
    d = new_decision(str(r.get("shipment_id", "UNKNOWN")))
    if validate_record(r, d, now):
        for rule in (rule_perfect_storm, rule_ai_insights, rule_asset_reallocation, rule_dynamic_insurance):
            rule(r, d)
        rule_low_risk_validation(r, d, db_records, now)  # after the risk-raising rules: only checks "Low"
        for rule in (rule_inventory_replacement, decide_outcome, check_financial_threshold):
            rule(r, d)
        if d["needs_human"]:  # final gate: anything needing a human is never fully automatic
            if d["outcome"] == "PROCEED":
                d["outcome"] = "ESCALATE"
            d["actions"].append("Route to human review queue")
    r.pop("_dropped_items", None)
    return r, d


def evaluate_shipments(assessments, db_records, now=None):
    """Evaluate every row of ai_manager.assess_shipments(); returns [(record, decision), ...]."""
    return [evaluate_shipment(row, db_records, now) for row in assessments.to_dict("records")]


# ---------------- Offline test (sample AI responses, no API calls) ----------------
if __name__ == "__main__":
    now = datetime(2026, 9, 28, 9, 0)
    base = {"shipment_id": "SHP-001", "origin_port": "SGSIN", "origin_lat": 1.266667, "origin_lon": 103.833333,
            "destination_port": "NLRTM", "destination_lat": 51.933333, "destination_lon": 4.133333,
            "departure_time": "01/10/2026", "arrival_time": "30/10/2026", "primary_risk_factor": "weather",
            "affected_location": "Strait of Malacca", "expected_impact": "Delay", "confidence_score": 0.82,
            "sources": ["open_meteo_weather", "gdelt_news"], "conflicting_sources": False, "extreme_event": "none",
            "insights": [], "alternative_route": None,
            "external_data_fetched_at": (now - timedelta(hours=1)).isoformat()}

    def factor(t, sev, loc="Route", src="open_meteo_weather", ind="-"):
        return {"type": t, "severity": sev, "location": loc, "source": src, "detail": ind}

    def insight(code, rt, sev, loc="Route", days=0):
        return dict(zip(INSIGHT_KEYS, (code, rt, sev, loc, days)))

    cases = {
        "Perfect Storm (perishable, reroute too long)": {**base, "risk_factors": [
            factor("weather", "Medium", "Strait of Malacca", ind="wind_gust_kmh=55"),
            factor("port_congestion", "Medium", "NLRTM", "gdelt_news", "news_articles=3"),
            factor("labor_shortage", "Medium", "NLRTM", "gdelt_news", "news_articles=2")],
            "goods": {"description": "Fresh fruit", "perishable": True},
            "alternative_route": {"name": "Cape of Good Hope", "distance_km": 20000}},
        "Piracy": {**base, "shipment_id": "SHP-002", "primary_risk_factor": "piracy_threat",
                   "affected_location": "Singapore Strait", "risk_factors": [
                       factor("piracy_threat", "High", "Singapore Strait", "gdelt_news", "news_articles=4")]},
        "Low risk but bad history": {**base, "shipment_id": "SHP-003",
                                     "risk_factors": [factor("weather", "Low", ind="wind_gust_kmh=20")]},
        "Typhoon destroys cargo at origin": {
            **base, "shipment_id": "SHP-004", "origin_port": "CNSHA", "destination_port": "SGSIN",
            "affected_location": "CNSHA", "expected_impact": "Cargo Destruction", "extreme_event": "typhoon",
            "risk_factors": [factor("weather", "High", "CNSHA", ind="wind_gust_kmh=180")],
            "insights": [insight("EXTREME_EVENT", "weather", "High", "CNSHA", 10),
                         insight("OUTDATED_DATA", "none", "Low")]},
        "AI fallback response": {
            **base, "shipment_id": "SHP-005", "risk_factors": [], "sources": [], "confidence_score": 0.0,
            "conflicting_sources": True, "primary_risk_factor": "infrastructure_disruption",
            "affected_location": "Unknown", "expected_impact": "None",
            "insights": [insight("MISSING_DATA", "none", "High")]},
        "AI returned free text": {**base, "shipment_id": "SHP-006", "affected_location": "near Shanghai port",
                                  "risk_factors": [factor("weather", "Low")], "insights": ["Typhoon may cause delays."]},
        "Bad AI record": {"shipment_id": "SHP-007"},
    }
    history = [{"route_id": "SGSIN-NLRTM", "saved_at": (now - timedelta(days=10)).isoformat(),
                "flagged": False, "delayed": True}]

    for name, rec in cases.items():
        _, d = evaluate_shipment(rec, history, now)
        print(f"\n=== {name} ===")
        print("Outcome :", d["outcome"], "| Risk:", d["overall_risk"], "| Human:", d["needs_human"])
        print("Flags   :", d["flags"])
        print("Actions :", d["actions"])
        print("Alerts  :", [(a["recipient"], a["channels"]) for a in d["alerts"]])
        for line in d["rationale"]:
            print("  -", line)