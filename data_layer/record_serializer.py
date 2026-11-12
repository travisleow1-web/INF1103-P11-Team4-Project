import logging
from datetime import date, datetime, timezone
from typing import Iterable, List
from model.port_registry import PortRegistry
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.shipment import Shipment
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError


logger = logging.getLogger(__name__)


class RecordSerializer:
    """Turns a ShipmentRecord into a plain document and back. Dates are ISO strings in the document."""

    def __init__(self, ports: PortRegistry):
        self.__ports = ports            # stored documents keep only the port code

    def to_document(self, record: ShipmentRecord) -> dict:
        """A plain dict for storage: port codes, ISO dates, and the assessment and decision as dicts."""
        s = record.shipment
        return {
            "shipment_id": s.shipment_id,
            "origin": s.origin.code,
            "destination": s.destination.code,
            "departure": s.departure.isoformat(),
            "arrival": s.arrival.isoformat(),
            "assessment": record.assessment.to_dict(),
            "decision": record.decision.to_dict(),
            "saved_at": record.saved_at.isoformat(),
        }

    def from_documents(self, docs: Iterable[dict]) -> List[ShipmentRecord]:
        """Every record that can be read. A damaged document is skipped and logged, so one bad
        record does not hide all the others."""
        records = []
        for index, doc in enumerate(docs):
            try:
                records.append(self.from_document(doc))
            except StorageError as error:
                name = doc.get("shipment_id") if isinstance(doc, dict) else None
                logger.warning("Skipping saved record %s: %s", name or f"at position {index}", error)
        return records

    def from_document(self, doc: dict) -> ShipmentRecord:
        """Accepts ISO strings (JSON) or datetimes (MongoDB). A damaged document raises StorageError."""
        try:
            shipment = Shipment(
                doc["shipment_id"],
                self.__port(doc["origin"]),
                self.__port(doc["destination"]),
                self.__date(doc["departure"]),
                self.__date(doc["arrival"]),
            )
            return ShipmentRecord(shipment, AIAssessment.from_dict(self.__mapping(doc["assessment"])),
                                  Decision.from_dict(self.__mapping(doc["decision"])), self.__time(doc["saved_at"]))
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            raise StorageError(f"A saved record is damaged: {error!r}") from error

    def __port(self, code):
        port = self.__ports.find(code)
        if port is None:
            raise ValueError(f"unknown port {code}")
        return port

    def __mapping(self, value):
        if not isinstance(value, dict):
            raise ValueError("expected an object")
        return value

    def __date(self, value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(value)

    def __time(self, value):
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
