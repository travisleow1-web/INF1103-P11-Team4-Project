from dataclasses import dataclass
from datetime import date
from .port import Port


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    origin: Port
    destination: Port
    departure: date
    arrival: date
