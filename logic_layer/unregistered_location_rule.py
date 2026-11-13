from datetime import datetime
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.port_registry import PortRegistry
from model.shipment import Shipment
from .business_rule import BusinessRule


class UnregisteredLocationRule(BusinessRule):
    """Notes any factor or insight location that is not a registered port, so a reader can check it."""

    GENERAL_LOCATIONS = frozenset({"Route", "Unknown"})

    def __init__(self, ports: PortRegistry):
        self.__ports = ports  # association: used, not owned

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        """Add one note listing the unregistered locations. It does not change the risk or ask for a human."""
        locations = [f.location for f in assessment.risk_factors] + [i.location for i in assessment.insights]
        unknown = sorted({place for place in locations
                          if place not in self.GENERAL_LOCATIONS and self.__ports.find(place) is None})
        if unknown:
            decision.add_note(f"Locations not in the port list: {', '.join(unknown)}", Flag.UNREGISTERED_LOCATION)
