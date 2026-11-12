from typing import List, Tuple
from model.shipment import Shipment
from .validation_result import ValidationResult


class Preview:
    """Every submitted row after validation, numbered in the order it was read."""

    def __init__(self, results: List[Tuple[int, ValidationResult]]):
        self.__results = results        # list of (row_number, ValidationResult)

    def total(self) -> int:
        """How many rows were submitted."""
        return len(self.__results)

    def valid_shipments(self) -> List[Shipment]:
        """The shipments from the valid rows, in order, with their new IDs."""
        return [r.shipment for n, r in self.__results if r.is_valid()]

    def problems(self) -> List[Tuple[int, List[str]]]:
        """(row number, errors) for each invalid row."""
        return [(n, r.errors) for n, r in self.__results if not r.is_valid()]

    def has_problems(self) -> bool:
        """True if any row is invalid. Then nothing should be assessed."""
        return any(not r.is_valid() for n, r in self.__results)
