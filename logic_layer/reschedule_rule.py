from datetime import date, datetime
from typing import Optional
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.risk_level import RiskLevel
from model.shipment import Shipment
from .business_rule import BusinessRule
from .reschedule_plan import ReschedulePlan


class RescheduleRule(BusinessRule):
    """New feature: a High or Extreme risk on a shipment that has not left, plus a clear weather window
    found by the AI, becomes a suggested later departure with the same journey length.

    The AI only supplies the date (earliest_clear_departure). This rule decides whether to use it.
    It adds an action and a note and never changes the outcome or the risk.
    """

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        """Add the suggestion to the decision when a plan exists."""
        plan = self.plan_for(shipment, assessment, now.date())
        if plan is None:
            return
        decision.add_note(
            f"Reschedule: {plan.reason}, clear weather from {plan.new_departure:%d/%m/%Y}",
            action=f"Consider departing on {plan.new_departure:%d/%m/%Y} and arriving on "
                   f"{plan.new_arrival:%d/%m/%Y} instead of {plan.original_departure:%d/%m/%Y}")

    def plan_for(self, shipment: Shipment, assessment: AIAssessment, today: date) -> Optional[ReschedulePlan]:
        """A plan, or None when the shipment already left, the AI found no later clear date,
        or no risk factor is High or Extreme."""
        clear = assessment.earliest_clear_departure
        if clear is None or shipment.departure < today or clear <= shipment.departure:
            return None
        if not any(f.severity >= RiskLevel.HIGH for f in assessment.risk_factors):
            return None
        new_arrival = clear + (shipment.arrival - shipment.departure)
        reason = f"{assessment.primary_risk_factor.value.replace('_', ' ')} at {assessment.affected_location}"
        return ReschedulePlan(shipment.shipment_id, shipment.departure, shipment.arrival,
                              clear, new_arrival, reason, assessment)
