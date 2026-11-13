from datetime import date, datetime
from typing import List, Optional
from model.port import Port
from model.port_registry import PortRegistry
from model.shipment import Shipment
from .validation_result import ValidationResult


class ShipmentValidator:
    """Checks one raw row: required fields, known ports, DD/MM/YYYY dates, arrival after departure.

    Every field that is present is checked even when another is missing, so the user sees all the
    problems in a row at once. Messages use plain field names ("Arrival date is missing").
    """

    REQUIRED = ["origin_port", "destination_port", "departure_time", "arrival_time"]
    DATE_FORMAT = "%d/%m/%Y"

    def __init__(self, ports: PortRegistry):
        self.__ports = ports

    def check(self, row: dict, shipment_id: str) -> ValidationResult:
        """Collect every error in the row. A valid row becomes a Shipment with the given ID."""
        errors: List[str] = []
        origin = self.__check_port(row.get("origin_port"), "Origin", errors)
        destination = self.__check_port(row.get("destination_port"), "Destination", errors)
        departure = self.__check_date(row.get("departure_time"), "Departure", errors)
        arrival = self.__check_date(row.get("arrival_time"), "Arrival", errors)

        # Cross-field checks only when both sides are valid.
        if origin and destination and origin == destination:
            errors.append("Origin and destination are the same port")
        if departure and arrival and arrival <= departure:
            errors.append("Arrival must be after departure")

        if errors:
            return ValidationResult(None, errors)
        return ValidationResult(Shipment(shipment_id, origin, destination, departure, arrival), [])

    def read_date(self, value: str) -> Optional[date]:
        """Return a date for a DD/MM/YYYY string, or None. Also used by IOManager for search dates."""
        try:
            return datetime.strptime(str(value).strip(), self.DATE_FORMAT).date()
        except ValueError:
            return None

    def __check_port(self, value, label: str, errors: List[str]) -> Optional[Port]:
        text = str(value or "").strip()
        if not text:
            errors.append(f"{label} port is missing")
            return None
        port = self.__ports.find(text)
        if port is None:
            errors.append(f"{label}: unknown port '{text}'")
        return port

    def __check_date(self, value, label: str, errors: List[str]) -> Optional[date]:
        text = str(value or "").strip()
        if not text:
            errors.append(f"{label} date is missing")
            return None
        result = self.read_date(text)
        if result is None:
            errors.append(f"{label}: '{text}' is not a valid date (use DD/MM/YYYY)")
        return result
