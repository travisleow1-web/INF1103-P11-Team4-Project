from typing import List, Tuple
from model.shipment import Shipment
from .validation_result import ValidationResult


class Preview:
    def __init__(self, results: List[Tuple[int, ValidationResult]]):
        self.__results = results        # list of (row_number, ValidationResult)

    def total(self) -> int:
        return len(self.__results)

    def valid_shipments(self) -> List[Shipment]:
        return [r.shipment for n, r in self.__results if r.is_valid()]

    def problems(self) -> List[Tuple[int, List[str]]]:
        return [(n, r.errors) for n, r in self.__results if not r.is_valid()]

    def has_problems(self) -> bool:
        return any(not r.is_valid() for n, r in self.__results)
