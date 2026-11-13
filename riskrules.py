from datetime import datetime, timedelta

from logic.businessrule import BusinessRule
from logic.decision import RiskLevel


class DataQualityRule(BusinessRule):

    def __init__(self, config):
        self._config = config

    def apply(self, record, decision, now):
        cfg = self._config
        dropped = record.get("_dropped_items", 0)
        conf = record["confidence_score"]
        fetched = self._fetched_time(record)
        checks = (
            (dropped, "Malformed AI items dropped", f"Data quality: {dropped} malformed list item(s) dropped"),
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

    @staticmethod
    def _fetched_time(record):
        try:
            return datetime.fromisoformat(str(record.get("external_data_fetched_at")))
        except ValueError:
            return None  # missing or unreadable timestamp: skip the age check


class PerfectStormRule(BusinessRule):

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
