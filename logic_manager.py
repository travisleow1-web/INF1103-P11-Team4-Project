

from datetime import datetime

from logic.businessrule import BusinessRule
from logic.decision import Decision, RiskLevel
from logic.holdrules import InsuranceRule, ProcurementRule, RouteHistoryRule
from logic.outcomeresolver import OutcomeResolver
from logic.recordpreparer import InvalidRecordError, RecordPreparer
from logic.riskrules import AIInsightRule, DataQualityRule, PerfectStormRule
from logic.routehistory import DataManagerRouteHistory, RouteHistorySource
from logic.ruleconfig import RuleConfig

# Other managers and the tests can import these straight from logic_manager
__all__ = ["LogicManager", "Decision", "RiskLevel", "RuleConfig", "BusinessRule",
           "RouteHistorySource", "DataManagerRouteHistory", "InvalidRecordError"]


class LogicManager:

    def __init__(self, history_source, config=None):
        self._history_source = history_source
        self._build(config or RuleConfig())

    def _build(self, config):
        # Composition: these parts are created here and live only inside this LogicManager.
        self._config = config
        self._preparer = RecordPreparer()
        self._rules = [
            DataQualityRule(config),
            PerfectStormRule(config),
            AIInsightRule(config),
            InsuranceRule(),
            RouteHistoryRule(config, self._history_source),  # after the risk-raising rules
            ProcurementRule(),
        ]
        self._resolver = OutcomeResolver()

    @property
    def config(self):
        return self._config

    @property
    def rules(self):
        return tuple(self._rules)

    def update_config(self, config):
        if not isinstance(config, RuleConfig):
            raise TypeError("config must be a RuleConfig")
        self._build(config)

    def evaluate_shipment(self, ai_record, now=None):
        now = now or datetime.now()
        record = self._preparer.prepare(ai_record)
        decision = Decision(record.get("shipment_id", "UNKNOWN"))
        try:
            self._preparer.ensure_usable(record)
        except InvalidRecordError as err:
            decision.set_outcome("REJECT")
            decision.add_note(str(err), err.flag, human=True)
        else:
            for rule in self._rules:  # polymorphism: same call for every rule type
                rule.apply(record, decision, now)
            self._resolver.resolve(decision)
        record.pop("_dropped_items", None)
        return record, decision

    def evaluate_shipments(self, assessments, now=None):
        rows = assessments.to_dict("records") if hasattr(assessments, "to_dict") else list(assessments)
        results = []
        for row in rows:
            try:
                results.append(self.evaluate_shipment(row, now))
            except Exception as exc:  # keep the batch running; the row goes to a human
                decision = Decision(row.get("shipment_id", "UNKNOWN") if isinstance(row, dict) else "UNKNOWN")
                decision.set_outcome("REJECT")
                decision.add_note(f"Evaluation failed: {exc!r}", "Evaluation error", human=True)
                results.append((row, decision))
        return results
