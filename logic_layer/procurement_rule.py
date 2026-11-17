from datetime import datetime
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.shipment import Shipment
from .business_rule import BusinessRule


class ProcurementRule(BusinessRule):
    DESTRUCTION_IMPACTS = frozenset({"Cargo Destruction"})

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        destroyed = assessment.expected_impact in self.DESTRUCTION_IMPACTS
        place = assessment.affected_location.split(" - ")[0].strip().upper()
        at_origin = place == shipment.origin.code
        if destroyed and at_origin:
            decision.hold()
            decision.add_alert("procurement_team", ["email"],
                               f"Shipment {shipment.shipment_id} is at risk of destruction at "
                               f"{shipment.origin.name}. Consider reordering to avoid stock-out.")
            decision.add_note(f"Rule 5: Cargo Destruction @{shipment.origin.code} (origin)", Flag.PROCUREMENT_ALERT,
                              "Reorder goods immediately: the goods on this shipment")
