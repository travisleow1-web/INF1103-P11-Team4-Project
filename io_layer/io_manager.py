import logging
import re
import threading
from datetime import timedelta, timezone
from typing import List
from data_layer.data_manager import DataManager
from model.outcome import Outcome
from model.port_registry import PortRegistry
from model.risk_level import RiskLevel
from model.search_criteria import SearchCriteria
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError
from .preview import Preview
from .shipment_source import ShipmentSource
from .shipment_validator import ShipmentValidator

logger = logging.getLogger(__name__)
SGT = timezone(timedelta(hours=8), "SGT")


class IOManager:
    """Everything between the user and the app: input, validation, search and the data pages display.

    It takes raw strings in and returns plain dicts out. It never prints, never calls the AI or Logic,
    and only reads saved records (through DataManager.find).
    """

    def __init__(self, validator: ShipmentValidator, data: DataManager, ports: PortRegistry):
        self.__validator, self.__data, self.__ports = validator, data, ports   # data is only read
        self.__last_handed_out = 0              # highest number given to a preview that can run
        self.__numbering = threading.Lock()     # one IOManager serves every request thread

    def preview(self, *sources: ShipmentSource) -> Preview:
        """Read every source, validate each row, and number the valid ones SHP-001, SHP-002, ...

        Numbers continue from the highest saved or handed-out ID, so two submissions running at once never
        share an ID. Only a preview without problems uses up numbers. Unreadable records raise StorageError.
        """
        rows = [row for source in sources for row in source.read()]
        with self.__numbering:
            next_number, results = max(self.__last_number(), self.__last_handed_out) + 1, []
            for number, row in enumerate(rows, start=1):
                result = self.__validator.check(row, f"SHP-{next_number:03d}")
                next_number += result.is_valid()
                results.append((number, result))
            preview = Preview(results)
            if not preview.has_problems():
                self.__last_handed_out = next_number - 1
        return preview

    def search(self, fields: dict) -> dict:
        """fields is the raw search form: strings in, a display dict out."""
        criteria, errors = self.__to_criteria(fields)
        if errors:
            return self.show_error("; ".join(errors))
        try:
            records = self.__data.find(criteria)
        except StorageError as error:
            return self.show_error(str(error))
        if not records:
            return self.show_no_records()
        return {"kind": "results", "summary": self.show_summary(records),
                "records": [self.show_result(r) for r in records]}

    def show_input_form(self) -> dict:
        """Choices for the input and search forms: port labels, risk labels and outcome values."""
        return {"ports": self.__ports.labels(), "risk_levels": [level.label for level in RiskLevel],
                "outcomes": [outcome.value for outcome in Outcome]}

    def show_result(self, record: ShipmentRecord) -> dict:
        """Everything about one record, ready to display: DD/MM/YYYY dates, port labels, full details."""
        s = record.shipment
        return {"shipment_id": s.shipment_id, "origin": s.origin.label(), "destination": s.destination.label(),
                "departure": s.departure.strftime("%d/%m/%Y"), "arrival": s.arrival.strftime("%d/%m/%Y"),
                "ai_unavailable": record.assessment.is_fallback(), "assessed_at": self.__local_time(record.saved_at),
                "fetched_at": self.__local_time(record.assessment.fetched_at),
                "assessment": record.assessment.to_dict(), "decision": record.decision.to_dict()}

    def show_summary(self, records: List[ShipmentRecord]) -> List[dict]:
        """One short row per record for the results table."""
        rows = []
        for r in records:
            a, d = r.assessment.to_dict(), r.decision.to_dict()
            factors, primary = a.get("risk_factors", []), a.get("primary_risk_factor")
            severity = next((f["severity"] for f in factors if f["type"] == primary), "-")
            rows.append({"shipment_id": r.shipment.shipment_id,
                         "route": f"{r.shipment.origin.code} → {r.shipment.destination.code}",
                         "expected_impact": a.get("expected_impact"), "confidence_score": a.get("confidence_score"),
                         "primary_factor": primary, "primary_severity": severity,
                         "primary_risk": self.__risk_text(primary, severity), "n_risk_factors": len(factors),
                         "conflicting_sources": a.get("conflicting_sources"), "overall_risk": d["overall_risk"],
                         "outcome": d["outcome"], "needs_human": d["needs_human"],
                         "ai_unavailable": r.assessment.is_fallback()})
        return rows

    def show_no_records(self) -> dict:
        """The search result when nothing matches."""
        return {"kind": "empty", "message": "No records match."}

    def show_error(self, message: str) -> dict:
        """A search result that shows a message instead of records."""
        return {"kind": "error", "message": message}

    def __to_criteria(self, fields):
        errors, bad_date, read_date = [], ": '{value}' is not a valid date (use DD/MM/YYYY)", self.__validator.read_date
        origin = self.__read(fields.get("origin"), errors, self.__ports.find, "origin: unknown port '{value}'")
        destination = self.__read(fields.get("destination"), errors, self.__ports.find,
                                  "destination: unknown port '{value}'")
        start = self.__read(fields.get("departure_from"), errors, read_date, "from date" + bad_date)
        end = self.__read(fields.get("departure_to"), errors, read_date, "to date" + bad_date)
        if start and end and start > end:
            errors.append("from date is after to date")
        risks, outcomes = [level.label for level in RiskLevel], [o.value for o in Outcome]
        overall_risk = self.__read(fields.get("overall_risk"), errors, lambda text: RiskLevel.parse(text).label,
                                   "Overall risk: '{text}' is not one of " + ", ".join(risks))
        outcome = self.__read(fields.get("outcome"), errors, lambda text: Outcome(text.upper()).value,
                              "Outcome: '{text}' is not one of " + ", ".join(outcomes))
        shipment_id = str(fields.get("shipment_id") or "").strip().upper()
        return SearchCriteria(
            shipment_id=shipment_id or None, origin=origin.code if origin else None,
            destination=destination.code if destination else None, overall_risk=overall_risk, outcome=outcome,
            needs_human={"yes": True, "no": False}.get(str(fields.get("needs_human", "")).lower()),
            departure_from=start, departure_to=end), errors

    def __read(self, value, errors, read, problem):
        """A filter field: blank means any; a value read() rejects (None or ValueError) adds problem to errors."""
        text = str(value or "").strip()
        if not text:
            return None
        try:
            result = read(text)
        except ValueError:
            result = None
        if result is None:
            errors.append(problem.format(value=value, text=text))
        return result

    def __local_time(self, moment):
        """DD/MM/YYYY HH:MM in Singapore time, for display."""
        return moment.astimezone(SGT).strftime("%d/%m/%Y %H:%M SGT")

    def __risk_text(self, risk_type, severity):
        """'port_congestion', 'MEDIUM' -> 'Port congestion (Medium)'; no severity -> just the name."""
        name = str(risk_type or "none").replace("_", " ").capitalize()
        return name if severity == "-" else f"{name} ({str(severity).capitalize()})"

    def __last_number(self):
        try:
            records = self.__data.find(SearchCriteria())
        except StorageError as error:
            logger.warning("Cannot read saved records to number shipments: %s", error)
            raise StorageError("Cannot assign shipment IDs: saved records could not be read.") from error
        return max((int(m.group(1)) for r in records if (m := re.fullmatch(r"SHP-(\d+)", r.shipment.shipment_id))),
                   default=0)
