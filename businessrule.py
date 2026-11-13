"""BusinessRule: abstract base class every business rule inherits from."""

from abc import ABC, abstractmethod


class BusinessRule(ABC):
    """Contract every business rule follows. LogicManager runs them in list order."""

    @abstractmethod
    def apply(self, record, decision, now):
        """Inspect the prepared record and update the decision."""
