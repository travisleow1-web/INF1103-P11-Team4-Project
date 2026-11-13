import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional, Union
from .outcome import Outcome
from .risk_level import RiskLevel
from .shipment_record import ShipmentRecord


@dataclass
class SearchCriteria:
    """The search filters. Unset (None) filters match everything.

    matches() filters records in Python (JSON backend); to_query() builds the same filter for MongoDB.
    """

    shipment_id: Optional[str] = None
    origin: Optional[str] = None                                # port code
    destination: Optional[str] = None                           # port code
    overall_risk: Optional[Union[str, RiskLevel]] = None        # stored as the label, e.g. "High"
    outcome: Optional[Union[str, Outcome]] = None               # stored as the value, e.g. "ESCALATE"
    needs_human: Optional[bool] = None
    departure_from: Optional[date] = None                       # inclusive
    departure_to: Optional[date] = None                         # inclusive

    def __post_init__(self):
        """Accept RiskLevel and Outcome members as well as text, stored as the text saved records hold."""
        if isinstance(self.overall_risk, RiskLevel):
            self.overall_risk = self.overall_risk.label
        if isinstance(self.outcome, Outcome):
            self.outcome = self.outcome.value

    def to_dict(self) -> dict:
        """Only the filters the user filled in (False for needs_human still counts)."""
        return {k: v for k, v in vars(self).items() if v not in (None, "")}

    def matches(self, record: ShipmentRecord) -> bool:
        """True if a saved record passes every filter that is set. Text is compared ignoring case."""
        f = self.to_dict()
        shipment, decision = record.shipment, record.decision.to_dict()

        def same(a: object, b: object) -> bool:
            return str(a).upper() == str(b).upper()

        return all([
            "shipment_id" not in f or same(shipment.shipment_id, f["shipment_id"]),
            "origin" not in f or same(shipment.origin.code, f["origin"]),
            "destination" not in f or same(shipment.destination.code, f["destination"]),
            "overall_risk" not in f or same(decision.get("overall_risk"), f["overall_risk"]),
            "outcome" not in f or same(decision.get("outcome"), f["outcome"]),
            "needs_human" not in f or decision.get("needs_human") == f["needs_human"],
            "departure_from" not in f or shipment.departure >= f["departure_from"],
            "departure_to" not in f or shipment.departure <= f["departure_to"],
        ])

    def to_query(self) -> dict:
        """The same filters as a MongoDB query. Risk and outcome live under 'decision.'."""
        f = self.to_dict()
        query = {}
        for key in ("shipment_id", "origin", "destination"):
            if key in f:
                query[key] = str(f[key]).upper()
        for key in ("overall_risk", "outcome"):
            if key in f:
                query[f"decision.{key}"] = {"$regex": f"^{re.escape(str(f[key]))}$", "$options": "i"}
        if "needs_human" in f:
            query["decision.needs_human"] = f["needs_human"]
        days = {}
        if "departure_from" in f:
            days["$gte"] = self.__midnight(f["departure_from"])
        if "departure_to" in f:
            days["$lte"] = self.__midnight(f["departure_to"])
        if days:
            query["departure"] = days
        return query

    def __midnight(self, day: date) -> datetime:
        return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
