from datetime import datetime
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.risk_level import RiskLevel
from model.shipment import Shipment
from .business_rule import BusinessRule


class RescheduleRule(BusinessRule):
    """Rule 6 (multi-condition): High or worse risk and a later clear window from the AI -> suggest new dates.

    Based on Travis's RescheduleManager. The AI only reports the earliest clear departure date it found in
    the forecast; this rule decides whether to suggest it. It runs after the risk-raising rules so it sees the
    final risk, and it adds an action for the planner without changing the outcome.
    """

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        """Suggest moving the shipment to the AI's clear window, keeping the same journey length."""
        clear_date = assessment.earliest_clear_departure
        if decision.risk_level < RiskLevel.HIGH or clear_date is None or clear_date <= shipment.departure:
            return
        new_arrival = clear_date + (shipment.arrival - shipment.departure)
        cause = assessment.primary_risk_factor.value.replace("_", " ")
        decision.add_note(
            f"Rule 6: risk {decision.overall_risk} with a clear window from {clear_date:%d/%m/%Y} "
            f"({cause} @{assessment.affected_location})", Flag.RESCHEDULE_SUGGESTED,
            f"Reschedule: depart {clear_date:%d/%m/%Y}, arrive {new_arrival:%d/%m/%Y}")
