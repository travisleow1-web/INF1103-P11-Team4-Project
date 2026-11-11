import re
from .preview import Preview
from .search_criteria import SearchCriteria
from .storage_error import StorageError


class IOManager:
    def __init__(self, validator, data, ports):
        self.__validator = validator
        self.__data = data              # DataManager: IO only reads from it
        self.__ports = ports            # PortRegistry

    def preview(self, *sources):
        """Read every source, validate each row, and number the valid ones SHP-001, SHP-002, ..."""
        rows = []
        for source in sources:
            rows.extend(source.read())

        next_number = self.__last_number() + 1
        results = []
        for number, row in enumerate(rows, start=1):
            result = self.__validator.check(row, f"SHP-{next_number:03d}")
            if result.is_valid():
                next_number += 1
            results.append((number, result))
        return Preview(results)

    def search(self, fields):
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

    # The show_* methods return the data a web template needs. They do not print.
    def show_input_form(self):
        return {"ports": self.__ports.labels()}

    def show_result(self, record):
        s = record.shipment
        return {
            "shipment_id": s.shipment_id,
            "origin": s.origin.label(),
            "destination": s.destination.label(),
            "departure": s.departure.strftime("%d/%m/%Y"),
            "arrival": s.arrival.strftime("%d/%m/%Y"),
            "ai_unavailable": record.assessment.is_fallback(),
            "assessment": record.assessment.to_dict(),
            "decision": record.decision.to_dict(),
        }

    def show_summary(self, records):
        rows = []
        for r in records:
            a = r.assessment.to_dict()
            d = r.decision.to_dict()
            factors = a.get("risk_factors", [])
            primary = a.get("primary_risk_factor")
            rows.append({
                "shipment_id": r.shipment.shipment_id,
                "route": f"{r.shipment.origin.code} -> {r.shipment.destination.code}",
                "expected_impact": a.get("expected_impact"),
                "confidence_score": a.get("confidence_score"),
                "primary_factor": primary,
                "primary_severity": next((f["severity"] for f in factors if f["type"] == primary), "-"),
                "n_risk_factors": len(factors),
                "conflicting_sources": a.get("conflicting_sources"),
                "overall_risk": d["overall_risk"],
                "outcome": d["outcome"],
                "needs_human": d["needs_human"],
                "ai_unavailable": r.assessment.is_fallback(),
            })
        return rows

    def show_no_records(self):
        return {"kind": "empty", "message": "No records match."}

    def show_error(self, message):
        return {"kind": "error", "message": message}

    def __to_criteria(self, fields):
        errors = []
        origin = self.__read_port(fields.get("origin"), "origin", errors)
        destination = self.__read_port(fields.get("destination"), "destination", errors)
        start = self.__read_date(fields.get("departure_from"), "from date", errors)
        end = self.__read_date(fields.get("departure_to"), "to date", errors)
        if start and end and start > end:
            errors.append("from date is after to date")
        shipment_id = self.__text(fields.get("shipment_id"))
        criteria = SearchCriteria(
            shipment_id=shipment_id.upper() if shipment_id else None,
            origin=origin.code if origin else None,
            destination=destination.code if destination else None,
            overall_risk=self.__text(fields.get("overall_risk")),
            outcome=self.__text(fields.get("outcome")),
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

    def __read_date(self, value, label, errors):
        text = str(value or "").strip()
        if not text:
            return None
        result = self.__validator.read_date(text)
        if result is None:
            errors.append(f"{label}: '{value}' is not a valid date (use DD/MM/YYYY)")
        return result

    def __text(self, value):
        return str(value or "").strip() or None

    def __last_number(self):
        try:
            records = self.__data.find(SearchCriteria())
        except StorageError:
            return 0
        numbers = [int(m.group(1)) for r in records
                   if (m := re.fullmatch(r"SHP-(\d+)", r.shipment.shipment_id))]
        return max(numbers, default=0)
