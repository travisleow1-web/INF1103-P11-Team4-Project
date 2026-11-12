from abc import ABC, abstractmethod
from datetime import datetime
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.shipment import Shipment


class BusinessRule(ABC):
    """Contract every business rule follows. LogicManager runs them in list order.

    Based on Jun Jie's BusinessRule (Logic_ManagerPart2), with typed inputs in place of a record dict.
    """

    @property
    def name(self) -> str:
        """The rule's name, used in logs and error notes."""
        return type(self).__name__

    @abstractmethod
    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        """Inspect the shipment and the AI's assessment, and update the decision through its methods."""
