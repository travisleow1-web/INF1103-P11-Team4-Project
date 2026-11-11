from dataclasses import dataclass
from datetime import date


@dataclass
class SearchCriteria:
    shipment_id: str = None
    origin: str = None              # port code
    destination: str = None         # port code
    overall_risk: str = None
    outcome: str = None
    needs_human: bool = None
    departure_from: date = None     # inclusive
    departure_to: date = None       # inclusive

    def to_dict(self):
        """Only the filters the user filled in (False for needs_human still counts)."""
        return {k: v for k, v in vars(self).items() if v not in (None, "")}
