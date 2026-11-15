from typing import List, Optional
from model.shipment import Shipment


class ValidationResult:
    """The outcome of checking one row: a Shipment when valid, otherwise every error found."""

    def __init__(self, shipment: Optional[Shipment], errors: List[str]):
        self.__shipment, self.__errors = shipment, errors

    def is_valid(self) -> bool:
        """True when the row had no errors."""
        return not self.__errors

    @property
    def shipment(self) -> Optional[Shipment]: return self.__shipment
    @property
    def errors(self) -> List[str]: return list(self.__errors)
