from abc import ABC, abstractmethod
from datetime import datetime
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.shipment import Shipment


class BusinessRule(ABC):
    @property
    def name(self) -> str:
        return type(self).__name__

    @abstractmethod
    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        ...
