

from abc import ABC, abstractmethod


class BusinessRule(ABC):
    

    @abstractmethod
    def apply(self, record, decision, now):
        """Inspect the prepared record and update the decision."""
