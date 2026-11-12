from datetime import datetime
from typing import TYPE_CHECKING
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.insight import Insight
from model.risk_level import RiskLevel
from model.shipment import Shipment
from .business_rule import BusinessRule

if TYPE_CHECKING:
    from .rule_config import RuleConfig


class AIInsightRule(BusinessRule):
    """Rule 1b: data-quality codes need a human; long delays and High or Extreme MULTIPLE_RISKS raise risk.

    Based on Jun Jie's AIInsightRule (Logic_ManagerPart2).
    """

    DATA_QUALITY_CODES = frozenset({"CONFLICTING_DATA", "OUTDATED_DATA", "MISSING_DATA", "NEEDS_HUMAN_REVIEW"})

    def __init__(self, config: "RuleConfig"):
        self.__config = config

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        """Act on the AI's coded insights."""
        insights = assessment.insights
        for insight in insights:
            if insight.code in self.DATA_QUALITY_CODES:
                decision.add_note(f"Rule 1b: {self.describe(insight)} -> human review", Flag.AI_FLAGGED, human=True)

        delays = [i for i in insights if i.code == "POTENTIAL_DELAY"]
        worst = max(delays, key=lambda i: i.estimated_delay_days, default=None)
        if worst is not None and worst.estimated_delay_days >= self.__config.delay_days_limit:
            high = worst.estimated_delay_days >= self.__config.delay_days_high
            decision.raise_risk(RiskLevel.HIGH if high else RiskLevel.MEDIUM)
            decision.add_note(f"Rule 1b: {self.describe(worst)} -> risk {decision.overall_risk}",
                              Flag.SIGNIFICANT_DELAY)

        for insight in insights:
            if insight.code == "MULTIPLE_RISKS" and insight.severity >= RiskLevel.HIGH:
                level = max(RiskLevel.HIGH, insight.severity)
                decision.raise_risk(level)
                decision.add_note(f"Rule 1b: {self.describe(insight)} -> risk {level.label}", Flag.COMPOUND_RISK)

    @staticmethod
    def describe(insight: Insight) -> str:
        """Short text for the rationale, for example 'POTENTIAL_DELAY weather/High @CNSHA +8d'."""
        days = f" +{insight.estimated_delay_days}d" if insight.estimated_delay_days else ""
        return f"{insight.code} {insight.risk_type.value}/{insight.severity.label} @{insight.location}{days}"
