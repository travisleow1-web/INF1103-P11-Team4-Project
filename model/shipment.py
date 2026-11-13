from dataclasses import dataclass
from datetime import date
from .port import Port


@dataclass(frozen=True)
class Shipment:
    """One shipment to assess: where it goes and when."""

    shipment_id: str
    origin: Port
    destination: Port
    departure: date
    arrival: date

    def route_id(self) -> str:
        """The route as origin and destination codes, for example 'SGSIN-NLRTM'."""
        return f"{self.origin.code}-{self.destination.code}"
