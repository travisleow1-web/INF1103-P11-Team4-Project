from datetime import datetime
from typing import TYPE_CHECKING
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from model.shipment import Shipment
from .business_rule import BusinessRule

if TYPE_CHECKING:
    from .rule_config import RuleConfig


class PerfectStormRule(BusinessRule):
    """Rule 1: a High or Extreme factor raises the risk to it; enough Medium storm factors make it High.

    Based on Jun Jie's PerfectStormRule (Logic_ManagerPart2).
    """

    STORM_FACTORS = frozenset({RiskType.WEATHER, RiskType.PORT_CONGESTION, RiskType.LABOR_SHORTAGE})

    def __init__(self, config: "RuleConfig"):
        self.__config = config

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        """Raise the risk from the factor severities (the worst severity of each type counts)."""
        levels = {}
        for factor in assessment.risk_factors:
            levels[factor.type] = max(levels.get(factor.type, RiskLevel.LOW), factor.severity)

        worst = max(levels.values(), default=RiskLevel.LOW)
        if worst >= RiskLevel.HIGH:
            decision.raise_risk(worst)
            decision.add_note(f"Rule 1: at least one risk factor is {worst.label}")

        mediums = sorted(t.value for t in self.STORM_FACTORS if levels.get(t, RiskLevel.LOW) >= RiskLevel.MEDIUM)
        if len(mediums) >= self.__config.perfect_storm_min_mediums:
            decision.raise_risk(RiskLevel.HIGH)
            decision.add_note(f"Rule 1 (Perfect Storm): {', '.join(mediums)} all >= Medium, upgraded to High",
                              Flag.PERFECT_STORM)
        elif worst >= RiskLevel.MEDIUM:
            decision.raise_risk(RiskLevel.MEDIUM)
