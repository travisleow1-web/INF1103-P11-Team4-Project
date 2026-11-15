from datetime import date, datetime
from typing import Optional
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from model.shipment import Shipment
from .business_rule import BusinessRule
from .reschedule_plan import ReschedulePlan


class RescheduleRule(BusinessRule):
    """New feature: a High or Extreme weather risk on a shipment that has not left, plus a clear weather window
    found by the AI, becomes a suggested later departure with the same journey length.

    The AI only supplies the date (earliest_clear_departure). This rule decides whether to use it and
    writes the reasoning from the assessment's own facts. It never changes the outcome or the risk.
    """

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        """Put the suggestion, with its reasoning, on the decision when a plan exists."""
        plan = self.plan_for(shipment, assessment, now.date())
        if plan is None:
            return
        reasoning = self.__reasoning(plan, assessment)
        decision.suggest_reschedule(plan.new_departure, plan.new_arrival, reasoning)
        decision.add_note(f"Reschedule: {reasoning}",
                          action=f"Consider departing on {plan.new_departure:%d/%m/%Y} and arriving on "
                                 f"{plan.new_arrival:%d/%m/%Y} instead of {plan.original_departure:%d/%m/%Y}")

    def plan_for(self, shipment: Shipment, assessment: AIAssessment, today: date) -> Optional[ReschedulePlan]:
        """A plan, or None when the shipment already left, the AI found no later clear date,
        or no weather risk factor is High or Extreme."""
        clear = assessment.earliest_clear_departure
        if clear is None or shipment.departure < today or clear <= shipment.departure:
            return None
        if not self.__weather_problems(assessment):
            return None
        new_arrival = clear + (shipment.arrival - shipment.departure)
        reason = f"{assessment.primary_risk_factor.value.replace('_', ' ')} at {assessment.affected_location}"
        return ReschedulePlan(shipment.shipment_id, shipment.departure, shipment.arrival,
                              clear, new_arrival, reason, assessment)

    @staticmethod
    def __weather_problems(assessment: AIAssessment) -> list:
        return [f for f in assessment.risk_factors if f.type is RiskType.WEATHER and f.severity >= RiskLevel.HIGH]

    def __reasoning(self, plan: ReschedulePlan, assessment: AIAssessment) -> str:
        """Why the planned dates are poor and why the new ones are better, from the assessment's facts."""
        problems = "; ".join(f"{f.severity.label} weather risk at {f.location} ({f.detail})"
                             for f in self.__weather_problems(assessment))
        days = plan.days_later
        journey = (plan.original_arrival - plan.original_departure).days
        return (f"Departing on {plan.original_departure:%d/%m/%Y} meets {problems}. "
                f"The AI found the earliest clear weather window in the forecast starting {plan.new_departure:%d/%m/%Y}, "
                f"{days} day{'' if days == 1 else 's'} later. Keeping the same {journey}-day journey, "
                f"the shipment would arrive on {plan.new_arrival:%d/%m/%Y} instead of "
                f"{plan.original_arrival:%d/%m/%Y}.")
