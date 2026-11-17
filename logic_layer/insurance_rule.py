from datetime import datetime
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from model.shipment import Shipment
from .business_rule import BusinessRule


class InsuranceRule(BusinessRule):
    TRIGGERS = frozenset({RiskType.PIRACY_THREAT, RiskType.SEVERE_CIVIL_UNREST})

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        present = {f.type for f in assessment.risk_factors} | {assessment.primary_risk_factor}
        triggered = sorted(t.value for t in self.TRIGGERS & present)
        if triggered:
            decision.hold()
            decision.raise_risk(RiskLevel.HIGH)
            decision.add_note(f"Rule 4: {', '.join(triggered)} detected, holding until insurance confirmed",
                              Flag.PREMIUM_INCREASE, "Update financial profile: extended insurance needed",
                              human=True)
