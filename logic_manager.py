from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import IntEnum

import validator
from config import (ALLOWED_IMPACT, ALLOWED_LOCATIONS, ALLOWED_RISK_TYPES,
                    ALLOWED_SEVERITY, INSIGHT_CODES, INSIGHT_RISK_TYPES)

# Thresholds and rule inputs (change them here, not inside the rules)
class RiskLevel(IntEnum):
    """Ordered risk levels, so they can be compared (LOW < MEDIUM < HIGH)."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def from_text(cls, text):
        """'Medium' / 'medium' / 'MEDIUM' -> RiskLevel.MEDIUM. Unknown text counts as LOW."""
        return cls.__members__.get(str(text).strip().upper(), cls.LOW)

    @property
    def label(self):
        """Display form used in decisions: 'Low' / 'Medium' / 'High'."""
        return self.name.capitalize()


class RuleConfig:
    """Every business-rule threshold in one validated object (new feature: user-configurable rules)."""

    _DEFAULTS = {
        "confidence_min": 0.60,           # below this, AI output needs a human
        "history_window_days": 21,        # Rule 3 look-back
        "perfect_storm_min_mediums": 3,   # Rule 1
        "data_max_age_hours": 24,         # external data older than this is "outdated"
        "delay_days_limit": 3,            # Rule 1b: delay that raises risk to Medium
        "delay_days_high": 7,             # Rule 1b: delay that raises risk to High
    }
    _WHOLE_NUMBER_KEYS = ("history_window_days", "perfect_storm_min_mediums",
                          "data_max_age_hours", "delay_days_limit", "delay_days_high")

    def __init__(self, **overrides):
        unknown = set(overrides) - set(self._DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown rule setting(s): {sorted(unknown)}")
        values = {**self._DEFAULTS, **overrides}
        self._validate(values)
        self._values = values

    @classmethod
    def _validate(cls, values):
        conf = values["confidence_min"]
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
            raise ValueError("confidence_min must be a number between 0 and 1")
        for key in cls._WHOLE_NUMBER_KEYS:
            value = values[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{key} must be a whole number of at least 1")
        if values["perfect_storm_min_mediums"] > len(PerfectStormRule.STORM_FACTORS):
            raise ValueError("perfect_storm_min_mediums cannot exceed the number of storm factors (3)")
        if values["delay_days_high"] < values["delay_days_limit"]:
            raise ValueError("delay_days_high must be at least delay_days_limit")

    @classmethod
    def from_dict(cls, data):
        """Rebuild a config from saved JSON data (keys not given keep their defaults)."""
        return cls(**dict(data))

    def to_dict(self):
        return dict(self._values)

    @property
    def confidence_min(self):
        return self._values["confidence_min"]

    @property
    def history_window_days(self):
        return self._values["history_window_days"]

    @property
    def perfect_storm_min_mediums(self):
        return self._values["perfect_storm_min_mediums"]

    @property
    def data_max_age_hours(self):
        return self._values["data_max_age_hours"]

    @property
    def delay_days_limit(self):
        return self._values["delay_days_limit"]

    @property
    def delay_days_high(self):
        return self._values["delay_days_high"]


class Decision:
    """The verdict on one shipment. State is private; rules change it only through methods."""

    OUTCOMES = ("PROCEED", "DELAY", "INSURE", "ESCALATE", "REJECT")

    def __init__(self, shipment_id):
        self._shipment_id = str(shipment_id)
        self._risk = RiskLevel.LOW
        self._outcome = "PROCEED"
        self._hold_shipment = False
        self._needs_human = False
        self._flags = []
        self._actions = []
        self._alerts = []
        self._rationale = []

    @property
    def shipment_id(self):
        return self._shipment_id

    @property
    def risk_level(self):
        return self._risk

    @property
    def overall_risk(self):
        return self._risk.label

    @property
    def outcome(self):
        return self._outcome

    @property
    def hold_shipment(self):
        return self._hold_shipment

    @property
    def needs_human(self):
        return self._needs_human

    @property
    def flags(self):
        return tuple(self._flags)

    @property
    def actions(self):
        return tuple(self._actions)

    @property
    def alerts(self):
        return tuple(dict(a) for a in self._alerts)

    @property
    def rationale(self):
        return tuple(self._rationale)

    def has_flag(self, flag):
        return flag in self._flags

    def add_note(self, why, flag=None, action=None, human=False):
        """Record why a rule fired, plus an optional flag (no duplicates), action and human-review request."""
        if human:
            self._needs_human = True
        if flag and flag not in self._flags:
            self._flags.append(flag)
        if action:
            self._actions.append(action)
        self._rationale.append(why)

    def add_action(self, action):
        self._actions.append(action)

    def raise_risk(self, level):
        """Risk only ever goes up; a later rule cannot undo an earlier High."""
        if level > self._risk:
            self._risk = level

    def hold(self):
        self._hold_shipment = True

    def require_human(self):
        self._needs_human = True

    def add_alert(self, recipient, channels, message):
        self._alerts.append({"recipient": recipient, "channels": list(channels), "message": message})

    def set_outcome(self, outcome):
        if outcome not in self.OUTCOMES:
            raise ValueError(f"Unknown outcome {outcome!r}")
        self._outcome = outcome

    def to_dict(self):
        """Plain dict for the Data Manager (saving) and IO Manager (display)."""
        return {"shipment_id": self._shipment_id, "overall_risk": self.overall_risk,
                "outcome": self._outcome, "hold_shipment": self._hold_shipment,
                "needs_human": self._needs_human, "flags": list(self._flags),
                "actions": list(self._actions), "alerts": [dict(a) for a in self._alerts],
                "rationale": list(self._rationale)}

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

def rule_low_risk_validation(r, d, db_records, now):
    """Rule 3: a 'Low' route flagged or delayed in the last 21 days needs dispatcher sign-off."""
    if d["overall_risk"] != "Low":
        return
    try:
        past = data_manager.get_route_history(db_records, r["route_id"], now - timedelta(days=HISTORY_WINDOW_DAYS))
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
        d["alerts"].append({"recipient": "procurement_team", "channels": ["email"], "message":
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

def evaluate_shipment(ai_record, db_records, now=None):
    """Run one AI row through every rule. Returns (prepared record, decision dict)."""
    now = now or datetime.now()
    r = prepare_record(ai_record)
    d = new_decision(str(r.get("shipment_id", "UNKNOWN")))
    if validate_record(r, d, now):
        for rule in (rule_perfect_storm, rule_ai_insights, rule_dynamic_insurance):
            rule(r, d)
        rule_low_risk_validation(r, d, db_records, now)  # after the risk-raising rules: only checks "Low"
        rule_inventory_replacement(r, d)
        decide_outcome(d)
        if d["needs_human"]:  # final gate: anything needing a human is never fully automatic
            d["outcome"] = "ESCALATE" if d["outcome"] == "PROCEED" else d["outcome"]
            d["actions"].append("Route to human review queue")
    r.pop("_dropped_items", None)
    return r, d

def evaluate_shipments(assessments, db_records, now=None):
    """Evaluate every row of ai_manager.assess_shipments(); returns [(record, decision), ...]."""
    results = []
    for row in assessments.to_dict("records"):
        try:
            results.append(evaluate_shipment(row, db_records, now))
        except Exception as exc:
            d = new_decision(str(row.get("shipment_id", "UNKNOWN")))
            d["outcome"] = "REJECT"
            _note(d, f"Evaluation failed: {exc!r}", "Evaluation error", human=True)
            results.append((row, d))
    return results