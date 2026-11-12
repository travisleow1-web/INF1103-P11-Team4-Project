from datetime import datetime
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.shipment import Shipment
from .business_rule import BusinessRule


class ProcurementRule(BusinessRule):
    """Rule 5 (multi-condition): Cargo Destruction predicted at the origin port -> reorder the goods.

    Based on Jun Jie's ProcurementRule (Logic_ManagerPart2).
    """

    DESTRUCTION_IMPACTS = frozenset({"Cargo Destruction"})

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        """Hold the shipment and alert procurement when the goods may be destroyed before they leave."""
        destroyed = assessment.expected_impact in self.DESTRUCTION_IMPACTS
        at_origin = assessment.affected_location == shipment.origin.code
        if destroyed and at_origin:
            decision.hold()
            decision.add_alert("procurement_team", ["email"],
                               f"Shipment {shipment.shipment_id} is at risk of destruction at "
                               f"{shipment.origin.name}. Consider reordering to avoid stock-out.")
            decision.add_note(f"Rule 5: Cargo Destruction @{shipment.origin.code} (origin)", Flag.PROCUREMENT_ALERT,
                              "Reorder goods immediately: the goods on this shipment")
