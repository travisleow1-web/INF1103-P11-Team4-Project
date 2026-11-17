from datetime import datetime, timezone
from typing import Optional
from .ai_assessment import AIAssessment
from .decision import Decision
from .outcome import Outcome
from .shipment import Shipment


class ShipmentRecord:
    def __init__(self, shipment: Shipment, assessment: AIAssessment, decision: Decision,
                 saved_at: Optional[datetime] = None):
        if saved_at is not None and saved_at.tzinfo is None:
            raise ValueError("saved_at must be timezone-aware")
        self.__shipment = shipment
        self.__assessment = assessment
        self.__decision = decision
        self.__saved_at = saved_at or datetime.now(timezone.utc)

    @property
    def shipment(self) -> Shipment:
        return self.__shipment

    @property
    def assessment(self) -> AIAssessment:
        return self.__assessment

    @property
    def decision(self) -> Decision:
        return self.__decision

    @property
    def saved_at(self) -> datetime:
        return self.__saved_at

    def is_delayed(self) -> bool:
        return self.__decision.outcome is Outcome.DELAY
