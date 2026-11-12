from datetime import date, datetime
from typing import Optional
from model.port_registry import PortRegistry
from model.shipment import Shipment
from .validation_result import ValidationResult


class ShipmentValidator:
    """Checks one raw row: required fields, known ports, DD/MM/YYYY dates, arrival after departure."""

    REQUIRED = ["origin_port", "destination_port", "departure_time", "arrival_time"]
    DATE_FORMAT = "%d/%m/%Y"

    def __init__(self, ports: PortRegistry):
        self.__ports = ports

    def check(self, row: dict, shipment_id: str) -> ValidationResult:
        """Collect every error in the row. A valid row becomes a Shipment with the given ID."""
        errors = []
        if not self.__check_required(row, errors):
            return ValidationResult(None, errors)      # cannot check the rest

        origin = self.__check_port(row["origin_port"], "origin", errors)
        destination = self.__check_port(row["destination_port"], "destination", errors)
        departure = self.__check_date(row["departure_time"], "departure", errors)
        arrival = self.__check_date(row["arrival_time"], "arrival", errors)

        if origin and destination and origin == destination:
            errors.append("origin and destination are the same port")
        if departure and arrival and arrival <= departure:
            errors.append("arrival must be after departure")

        if errors:
            return ValidationResult(None, errors)
        return ValidationResult(Shipment(shipment_id, origin, destination, departure, arrival), [])

    def read_date(self, value: str) -> Optional[date]:
        """Return a date for a DD/MM/YYYY string, or None. Also used by IOManager for search dates."""
        try:
            return datetime.strptime(str(value).strip(), self.DATE_FORMAT).date()
        except ValueError:
            return None

    def __check_required(self, row, errors):
        ok = True
        for name in self.REQUIRED:
            if not str(row.get(name) or "").strip():
                errors.append(f"{name} is missing")
                ok = False
        return ok

    def __check_port(self, value, label, errors):
        port = self.__ports.find(value)
        if port is None:
            errors.append(f"{label}: unknown port '{value}'")
        return port

    def __check_date(self, value, label, errors):
        result = self.read_date(value)
        if result is None:
            errors.append(f"{label}: '{value}' is not a valid date (use DD/MM/YYYY)")
        return result
