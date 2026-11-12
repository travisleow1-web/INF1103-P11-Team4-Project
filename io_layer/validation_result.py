from typing import List, Optional
from model.shipment import Shipment


class ValidationResult:
    """The outcome of checking one row: a Shipment when valid, otherwise every error found."""

    def __init__(self, shipment: Optional[Shipment], errors: List[str]):
        self.__shipment = shipment
        self.__errors = errors

    def is_valid(self) -> bool:
        """True when the row had no errors."""
        return len(self.__errors) == 0

    @property
    def shipment(self) -> Optional[Shipment]:
        return self.__shipment

    @property
    def errors(self) -> List[str]:
        return list(self.__errors)
