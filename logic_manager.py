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

class RouteHistorySource(ABC):
    """Contract: anything that can list past shipments on a route since a given time."""

    @abstractmethod
    def get_route_history(self, route_id, since):
        """Return a list of past-run dicts; a run may carry 'flagged' / 'delayed' booleans."""


class DataManagerRouteHistory(RouteHistorySource):
    """Adapts the Data Manager's stored records to the RouteHistorySource interface."""

    def __init__(self, db_records):
        self._db_records = db_records

    def get_route_history(self, route_id, since):
        import data_manager  # imported here so the Logic Manager can be tested without it
        return data_manager.get_route_history(self._db_records, route_id, since)    

class RecordPreparer:
    """Copies an AI row and fills in route_id, port names, defaults and cleaned lists."""

    INSIGHT_KEYS = ("code", "risk_type", "severity", "location", "estimated_delay_days")
    FACTOR_KEYS = ("type", "severity")

    def prepare(self, ai_record):
        """Return (prepared record, number of malformed list items dropped)."""
        record = dict(ai_record)  # never change the caller's data
        origin, destination = record.get("origin_port", ""), record.get("destination_port", "")
        record.setdefault("route_id", f"{origin}-{destination}")
        for key, code in (("origin", origin), ("destination", destination)):
            record.setdefault(key, self._port_name(code))
        if not isinstance(record.get("sources"), list):
            record["sources"] = []
        record["risk_factors"], bad_factors = self._clean_list(record.get("risk_factors"), self.FACTOR_KEYS)
        record["insights"], bad_insights = self._clean_list(record.get("insights"), self.INSIGHT_KEYS)
        for insight in record["insights"]:
            try:
                insight["estimated_delay_days"] = max(0, int(insight["estimated_delay_days"]))
            except (TypeError, ValueError):
                insight["estimated_delay_days"] = 0
        return record, bad_factors + bad_insights

    @staticmethod
    def _port_name(code):
        port = validator.PORTS_BY_CODE.get(code)
        return port["name"] if port else str(code)

    @staticmethod
    def _clean_list(value, keys):
        """Keep dict items that have every key (copied); also return how many were dropped."""
        if not isinstance(value, list):
            return [], 0
        good = [dict(item) for item in value if isinstance(item, dict) and all(k in item for k in keys)]
        return good, len(value) - len(good)


class RecordValidator:
    """Rejects unusable records and flags softer problems for human review."""

    REQUIRED_FIELDS = ("shipment_id", "origin_port", "destination_port", "risk_factors",
                       "primary_risk_factor", "affected_location", "expected_impact",
                       "confidence_score", "sources")

    def __init__(self, config, allowed_values=None):
        self._config = config
        self._allowed = allowed_values or {
            "risk_types": ALLOWED_RISK_TYPES, "locations": ALLOWED_LOCATIONS,
            "impacts": ALLOWED_IMPACT, "severities": ALLOWED_SEVERITY,
            "insight_codes": INSIGHT_CODES, "insight_risk_types": INSIGHT_RISK_TYPES,
        }

    def validate(self, record, dropped_items, decision, now):
        """Return False (and mark REJECT) when the record cannot be used at all."""
        missing = [f for f in self.REQUIRED_FIELDS if record.get(f) in (None, "")]
        conf = record.get("confidence_score")
        if missing or isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
            decision.set_outcome("REJECT")
            if missing:
                decision.add_note(f"Validation failed: missing fields {missing}",
                                  "Incomplete AI record", human=True)
            else:
                decision.add_note("Validation failed: confidence_score not in 0-1",
                                  "Invalid confidence score", human=True)
            return False

        cfg = self._config
        problems = self._schema_problems(record, dropped_items)
        fetched = self._fetched_time(record)
        checks = (
            (problems, "AI output outside schema", f"Validation: unexpected AI values {problems}"),
            (conf < cfg.confidence_min, "Low AI confidence",
             f"Confidence {conf:.2f} is below {cfg.confidence_min:.2f}"),
            (fetched and now - fetched > timedelta(hours=cfg.data_max_age_hours), "Outdated external data",
             f"External data is older than {cfg.data_max_age_hours}h"),
            (record.get("conflicting_sources") is True, "Conflicting sources",
             "AI reported conflicting or missing information"),
        )
        for failed, flag, why in checks:
            if failed:
                decision.add_note(why, flag, human=True)
        return True

    def _schema_problems(self, record, dropped_items):
        allowed = self._allowed
        checks = [("primary_risk_factor", record.get("primary_risk_factor"), allowed["risk_types"]),
                  ("affected_location", record.get("affected_location"), allowed["locations"]),
                  ("expected_impact", record.get("expected_impact"), allowed["impacts"])]
        for factor in record["risk_factors"]:
            checks += [("risk_factors.type", factor["type"], allowed["risk_types"]),
                       ("risk_factors.severity", factor["severity"], allowed["severities"])]
        for insight in record["insights"]:
            checks += [("insights.code", insight["code"], allowed["insight_codes"]),
                       ("insights.risk_type", insight["risk_type"], allowed["insight_risk_types"]),
                       ("insights.severity", insight["severity"], allowed["severities"])]
        problems = [f"{name}={value!r}" for name, value, ok in checks if value not in ok]
        if dropped_items:
            problems.append(f"{dropped_items} malformed list item(s) dropped")
        return problems

    @staticmethod
    def _fetched_time(record):
        try:
            return datetime.fromisoformat(str(record.get("external_data_fetched_at")))
        except ValueError:
            return None  # missing or unreadable timestamp: skip the age check

class BusinessRule(ABC):
    """Contract every business rule follows. LogicManager runs them in list order."""

    @abstractmethod
    def apply(self, record, decision, now):
        """Inspect the prepared record and update the decision."""


class PerfectStormRule(BusinessRule):
    """Rule 1: any High factor -> High; enough Medium weather/congestion/labour factors -> High."""

    STORM_FACTORS = frozenset({"weather", "port_congestion", "labor_shortage"})

    def __init__(self, config):
        self._config = config

    def apply(self, record, decision, now):
        levels = {}
        for factor in record["risk_factors"]:
            levels[factor["type"]] = max(levels.get(factor["type"], RiskLevel.LOW),
                                         RiskLevel.from_text(factor["severity"]))
        if RiskLevel.HIGH in levels.values():
            decision.raise_risk(RiskLevel.HIGH)
            decision.add_note("Rule 1: at least one risk factor is High")
        mediums = [f for f in self.STORM_FACTORS if levels.get(f, RiskLevel.LOW) >= RiskLevel.MEDIUM]
        if len(mediums) >= self._config.perfect_storm_min_mediums:
            decision.raise_risk(RiskLevel.HIGH)
            decision.add_note(f"Rule 1 (Perfect Storm): {', '.join(sorted(mediums))} all >= Medium, "
                              "upgraded to High", "Perfect Storm")
        elif RiskLevel.MEDIUM in levels.values():
            decision.raise_risk(RiskLevel.MEDIUM)


class AIInsightRule(BusinessRule):
    """Rule 1b: data-quality codes -> human; long predicted delays and High MULTIPLE_RISKS raise risk."""

    DATA_QUALITY_CODES = frozenset({"CONFLICTING_DATA", "OUTDATED_DATA", "MISSING_DATA", "NEEDS_HUMAN_REVIEW"})

    def __init__(self, config):
        self._config = config

    def apply(self, record, decision, now):
        insights = record["insights"]
        for insight in insights:
            if insight["code"] in self.DATA_QUALITY_CODES:
                decision.add_note(f"Rule 1b: {self._describe(insight)} -> human review",
                                  f"AI flagged: {insight['code']}", human=True)

        delays = [i for i in insights if i["code"] == "POTENTIAL_DELAY"]
        worst = max(delays, key=lambda i: i["estimated_delay_days"]) if delays else None
        if worst and worst["estimated_delay_days"] >= self._config.delay_days_limit:
            high = worst["estimated_delay_days"] >= self._config.delay_days_high
            decision.raise_risk(RiskLevel.HIGH if high else RiskLevel.MEDIUM)
            decision.add_note(f"Rule 1b: {self._describe(worst)} -> risk {decision.overall_risk}",
                              "Significant Delay Expected")

        for insight in insights:
            if insight["code"] == "MULTIPLE_RISKS" and RiskLevel.from_text(insight["severity"]) == RiskLevel.HIGH:
                decision.raise_risk(RiskLevel.HIGH)
                decision.add_note(f"Rule 1b: {self._describe(insight)} -> risk High", "Compound Risk")

    @staticmethod
    def _describe(insight):
        """e.g. 'POTENTIAL_DELAY weather/High @CNSHA +8d'."""
        days = f" +{insight['estimated_delay_days']}d" if insight["estimated_delay_days"] else ""
        return f"{insight['code']} {insight['risk_type']}/{insight['severity']} @{insight['location']}{days}"


class InsuranceRule(BusinessRule):
    """Rule 4: piracy_threat / severe_civil_unrest -> hold until extended insurance is confirmed."""

    TRIGGERS = frozenset({"piracy_threat", "severe_civil_unrest"})

    def apply(self, record, decision, now):
        present = {f["type"] for f in record["risk_factors"]} | {record["primary_risk_factor"]}
        triggered = self.TRIGGERS & present
        if triggered:
            decision.hold()
            decision.raise_risk(RiskLevel.HIGH)
            decision.add_note(f"Rule 4: {', '.join(sorted(triggered))} detected, holding until insurance "
                              "confirmed", "Premium Increase Required",
                              "Update financial profile: extended insurance needed", human=True)


class RouteHistoryRule(BusinessRule):
    """Rule 3: a 'Low' route flagged or delayed recently needs dispatcher sign-off."""

    def __init__(self, config, history_source):
        self._config = config
        self._history = history_source  # association: used, not owned

    def apply(self, record, decision, now):
        if decision.risk_level != RiskLevel.LOW:
            return  # only double-checks shipments that are still Low
        window = self._config.history_window_days
        try:
            past = self._history.get_route_history(record["route_id"], now - timedelta(days=window))
        except (KeyError, TypeError, ValueError) as exc:
            decision.add_note(f"Rule 3: could not read route history ({exc}), needs human",
                              "Route history unavailable", human=True)
            return
        problems = [p for p in past if p.get("flagged") or p.get("delayed")]
        if not problems:
            decision.add_note(f"Rule 3: Low risk and clean {window}-day history, auto-approve")
            return
        decision.hold()
        decision.add_note(f"Rule 3: AI says Low but {len(problems)} shipment(s) on route {record['route_id']} "
                          f"were flagged or delayed in the last {window} days", "Cautionary Override",
                          "Require human dispatcher sign-off", human=True)


class ProcurementRule(BusinessRule):
    """Rule 5 (multi-condition): Cargo Destruction predicted AT the origin port -> reorder the goods."""

    DESTRUCTION_IMPACTS = frozenset({"Cargo Destruction"})

    def apply(self, record, decision, now):
        destroyed = record["expected_impact"] in self.DESTRUCTION_IMPACTS
        at_origin = record["affected_location"] == record["origin_port"]
        if destroyed and at_origin:
            decision.hold()
            decision.add_alert("procurement_team", ["email"],
                               f"Shipment {record['shipment_id']} is at risk of destruction at "
                               f"{record['origin']}. Consider reordering to avoid stock-out.")
            decision.add_note(f"Rule 5: Cargo Destruction @{record['origin_port']} (origin)", "Procurement Alert",
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