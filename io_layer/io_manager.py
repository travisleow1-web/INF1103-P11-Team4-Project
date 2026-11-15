import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from data_layer.data_manager import DataManager
from model.outcome import Outcome
from model.port_registry import PortRegistry
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from model.shipment import Shipment
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

    def __init__(self, validator: ShipmentValidator, data: DataManager, ports: PortRegistry,
                 forecast_days: int = 16):
        self.__forecast_days = forecast_days    # how far ahead the AI can see the weather (for the report)
        self.__validator = validator
        self.__data = data              # IO only reads from it
        self.__ports = ports
        self.__last_handed_out = 0      # highest number given to a preview that can run
        self.__numbering = threading.Lock()   # one IOManager serves every request thread

    def preview(self, *sources: ShipmentSource) -> Preview:
        """Read every source, validate each row, and number the valid ones SHP-001, SHP-002, ...

        Numbers continue from the highest saved ID or the highest ID already handed out, whichever is
        larger, so two submissions running at the same time never share an ID (records are saved only
        as each shipment finishes). Only a preview without problems uses up numbers. If the saved
        records cannot be read, this raises StorageError instead of guessing.
        """
        rows = []
        for source in sources:
            rows.extend(source.read())

        with self.__numbering:
            next_number = max(self.__last_number(), self.__last_handed_out) + 1
            results = []
            for number, row in enumerate(rows, start=1):
                result = self.__validator.check(row, f"SHP-{next_number:03d}")
                if result.is_valid():
                    next_number += 1
                results.append((number, result))
            preview = Preview(results)
            if not preview.has_problems():
                self.__last_handed_out = next_number - 1
        return preview

    def shipments_to_rerun(self, shipment_ids: List[str]) -> "tuple[List[Shipment], List[str]]":
        """The saved shipments to assess again, for IDs whose record has no AI assessment (AI unavailable).

        Returns (shipments, skipped): skipped are IDs that are not saved or already have an AI assessment.
        If the saved records cannot be read, this raises StorageError.
        """
        shipments, skipped = [], []
        for shipment_id in dict.fromkeys(text.strip().upper() for text in shipment_ids if text.strip()):
            found = self.__data.find(SearchCriteria(shipment_id=shipment_id))
            saved = next((r for r in found if r.shipment.shipment_id == shipment_id), None)
            if saved and saved.assessment.is_fallback():
                shipments.append(saved.shipment)
            else:
                skipped.append(shipment_id)
        return shipments, skipped

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
                "records": [self.show_result(r) for r in records],
                "reschedule": self.show_reschedule(records),
                "report": self.show_report(records)}

    # The show_* methods return the data a web template needs. They do not print.
    def show_input_form(self) -> dict:
        """Choices for the input and search forms: port labels, risk labels and outcome values."""
        return {"ports": self.__ports.labels(),
                "risk_levels": [level.label for level in RiskLevel],
                "outcomes": [outcome.value for outcome in Outcome]}

    def show_result(self, record: ShipmentRecord) -> dict:
        """Everything about one record, ready to display: DD/MM/YYYY dates, port labels, full details."""
        s = record.shipment
        return {
            "shipment_id": s.shipment_id,
            "origin": s.origin.label(),
            "destination": s.destination.label(),
            "departure": s.departure.strftime("%d/%m/%Y"),
            "arrival": s.arrival.strftime("%d/%m/%Y"),
            "ai_unavailable": record.assessment.is_fallback(),
            "assessed_at": self.__local_time(record.saved_at),
            "fetched_at": self.__local_time(record.assessment.fetched_at),
            "assessment": record.assessment.to_dict(),
            "decision": record.decision.to_dict(),
        }

    def show_summary(self, records: List[ShipmentRecord]) -> List[dict]:
        """One short row per record for the results table."""
        rows = []
        for r in records:
            a = r.assessment.to_dict()
            d = r.decision.to_dict()
            factors = a.get("risk_factors", [])
            primary = a.get("primary_risk_factor")
            severity = next((f["severity"] for f in factors if f["type"] == primary), "-")
            rows.append({
                "shipment_id": r.shipment.shipment_id,
                "route": f"{r.shipment.origin.code} \u2192 {r.shipment.destination.code}",
                "expected_impact": a.get("expected_impact"),
                "confidence_score": a.get("confidence_score"),
                "primary_factor": primary,
                "primary_severity": severity,
                "primary_risk": self.__risk_text(primary, severity),
                "n_risk_factors": len(factors),
                "conflicting_sources": a.get("conflicting_sources"),
                "overall_risk": d["overall_risk"],
                "outcome": d["outcome"],
                "needs_human": d["needs_human"],
                "ai_unavailable": r.assessment.is_fallback(),
            })
        return rows

    def show_reschedule(self, records: List[ShipmentRecord]) -> List[dict]:
        """One row per High or Extreme risk shipment: its planned dates, the suggested dates and why.

        A shipment with no suggestion says why; suggested is then None.
        """
        rows = []
        for r in records:
            if r.decision.risk_level < RiskLevel.HIGH:
                continue
            s, plan = r.shipment, r.decision.reschedule
            row = {"shipment_id": s.shipment_id, "route": f"{s.origin.code} \u2192 {s.destination.code}",
                   "planned": f"{s.departure:%d/%m/%Y} to {s.arrival:%d/%m/%Y}", "suggested": None,
                   "days_later": None,
                   "reasoning": f"No new date suggested: {self.__reason_text(self.__no_date_code(r), 1)}."}
            if plan:
                new_departure = date.fromisoformat(plan["new_departure"])
                row.update(suggested=f"{new_departure:%d/%m/%Y} to "
                                     f"{date.fromisoformat(plan['new_arrival']):%d/%m/%Y}",
                           days_later=(new_departure - s.departure).days, reasoning=plan["reasoning"])
            rows.append(row)
        return rows

    def show_report(self, records: List[ShipmentRecord], not_saved: int = 0, planned: Optional[int] = None,
                    seconds: Optional[float] = None, finished_at: Optional[datetime] = None) -> dict:
        """The summary at the top of the results and search pages: counts, and what needs attention.

        not_saved is how many of these records could not be stored, planned how many shipments the run
        meant to assess (the report says so when it stopped early), seconds how long the run took.
        """
        total = len(records)
        high = [r for r in records if r.decision.risk_level >= RiskLevel.HIGH]
        failed = [r.shipment.shipment_id for r in records if r.assessment.is_fallback()]
        suggested = [r for r in high if r.decision.reschedule]
        without = [r for r in high if not r.decision.reschedule]
        return {
            "assessed": total,
            "saved": total - not_saved,
            "not_saved": not_saved,
            "stopped": f"Stopped after {total} of {planned} shipments." if planned and planned > total else None,
            "high_or_extreme": len(high),
            "needs_human": sum(1 for r in records if r.decision.needs_human),
            "ai_unavailable": len(failed),
            "ai_unavailable_ids": failed,
            "risk": self.__counts([r.decision.risk_level.label for r in records], [l.label for l in RiskLevel]),
            "outcome": self.__counts([r.decision.outcome.value for r in records], [o.value for o in Outcome],
                                     text=str.capitalize),
            "high_total": len(high),
            "suggested": len(suggested),
            "no_date": self.__no_date_text(without),
            "finished_at": self.__local_time(finished_at) if finished_at else None,
            "took": self.__duration(seconds),
        }

    def show_no_records(self) -> dict:
        """The search result when nothing matches."""
        return {"kind": "empty", "message": "No records match."}

    def show_error(self, message: str) -> dict:
        """A search result that shows a message instead of records."""
        return {"kind": "error", "message": message}

    def __to_criteria(self, fields):
        errors = []
        origin = self.__read_port(fields.get("origin"), "origin", errors)
        destination = self.__read_port(fields.get("destination"), "destination", errors)
        start = self.__read_date(fields.get("departure_from"), "from date", errors)
        end = self.__read_date(fields.get("departure_to"), "to date", errors)
        if start and end and start > end:
            errors.append("from date is after to date")
        overall_risk = self.__read_choice(fields.get("overall_risk"), "Overall risk", errors,
                                          lambda text: RiskLevel.parse(text).label,
                                          [level.label for level in RiskLevel])
        outcome = self.__read_choice(fields.get("outcome"), "Outcome", errors,
                                     lambda text: Outcome(text.upper()).value, [o.value for o in Outcome])
        shipment_id = self.__text(fields.get("shipment_id"))
        criteria = SearchCriteria(
            shipment_id=shipment_id.upper() if shipment_id else None,
            origin=origin.code if origin else None,
            destination=destination.code if destination else None,
            overall_risk=overall_risk,
            outcome=outcome,
            needs_human={"yes": True, "no": False}.get(str(fields.get("needs_human", "")).lower()),
            departure_from=start,
            departure_to=end,
        )
        return criteria, errors

    def __read_port(self, value, label, errors):
        text = str(value or "").strip()
        if not text:
            return None
        port = self.__ports.find(text)
        if port is None:
            errors.append(f"{label}: unknown port '{value}'")
        return port

    def __read_choice(self, value, label, errors, read, allowed):
        """A dropdown value: blank means any; anything not in the list is an error, not a silent no-match."""
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return read(text)
        except ValueError:
            errors.append(f"{label}: '{text}' is not one of {', '.join(allowed)}")
            return None

    def __read_date(self, value, label, errors):
        text = str(value or "").strip()
        if not text:
            return None
        result = self.__validator.read_date(text)
        if result is None:
            errors.append(f"{label}: '{value}' is not a valid date (use DD/MM/YYYY)")
        return result

    def __local_time(self, moment):
        """DD/MM/YYYY HH:MM in Singapore time, for display."""
        return moment.astimezone(SGT).strftime("%d/%m/%Y %H:%M SGT")

    @staticmethod
    def __counts(values, order, text=str):
        """[{"label", "count", "share"}] for each name in order, share being the percent of all values."""
        total = len(values) or 1
        return [{"label": text(name), "count": values.count(name), "share": round(100 * values.count(name) / total, 1)}
                for name in order]

    def __no_date_text(self, records) -> Optional[str]:
        """One sentence on why high-risk shipments got no new date, or None when every one got a date."""
        if not records:
            return None
        codes = [self.__no_date_code(r) for r in records]
        count = len(records)
        start = f"{count} {'has' if count == 1 else 'have'} none"
        if len(set(codes)) == 1:
            return f"{start} because {self.__reason_text(codes[0], count)}."
        parts = [f"{codes.count(code)} because {self.__reason_text(code, codes.count(code))}" for code in dict.fromkeys(codes)]
        return f"{start}: " + "; ".join(parts) + "."

    def __no_date_code(self, record: ShipmentRecord) -> str:
        s, assessed_on = record.shipment, record.saved_at.date()
        if s.departure < assessed_on:
            return "left"
        if s.arrival > assessed_on + timedelta(days=self.__forecast_days):
            return "forecast"
        if not any(f.type is RiskType.WEATHER and f.severity >= RiskLevel.HIGH
                   for f in record.assessment.risk_factors):
            return "not_weather"
        return "no_window"

    def __reason_text(self, code: str, count: int) -> str:
        """The reason in words, for one shipment or several."""
        one = count == 1
        days = self.__forecast_days
        return {"left": "it had already left" if one else "they had already left",
                "forecast": f"its arrival is after the {days}-day forecast" if one
                else f"their arrivals are after the {days}-day forecast",
                "not_weather": "its risk is not a weather problem" if one else "their risks are not weather problems",
                "no_window": "no clear day was found in the forecast"}[code]

    @staticmethod
    def __duration(seconds: Optional[float]) -> Optional[str]:
        if seconds is None:
            return None
        whole = max(0, round(seconds))
        return f"{whole // 60} min {whole % 60} s" if whole >= 60 else f"{whole} s"

    def __risk_text(self, risk_type, severity):
        """'port_congestion', 'MEDIUM' -> 'Port congestion (Medium)'; no severity -> just the name."""
        name = str(risk_type or "none").replace("_", " ").capitalize()
        return name if severity == "-" else f"{name} ({str(severity).capitalize()})"

    def __text(self, value):
        return str(value or "").strip() or None

    def __last_number(self):
        try:
            records = self.__data.find(SearchCriteria())
        except StorageError as error:
            logger.warning("Cannot read saved records to number shipments: %s", error)
            raise StorageError("Cannot assign shipment IDs: saved records could not be read.") from error
        numbers = [int(m.group(1)) for r in records
                   if (m := re.fullmatch(r"SHP-(\d+)", r.shipment.shipment_id))]
        return max(numbers, default=0)
