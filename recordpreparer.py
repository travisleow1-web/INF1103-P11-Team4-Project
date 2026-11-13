

import validator


class InvalidRecordError(ValueError):

    def __init__(self, message, flag):
        super().__init__(message)
        self.flag = flag  # short label shown in the decision's flags


class RecordPreparer:

    INSIGHT_KEYS = ("code", "risk_type", "severity", "location", "estimated_delay_days")
    FACTOR_KEYS = ("type", "severity")
    REQUIRED_FIELDS = ("shipment_id", "origin_port", "destination_port", "risk_factors",
                       "primary_risk_factor", "affected_location", "expected_impact",
                       "confidence_score", "sources")

    def prepare(self, ai_record):
        record = dict(ai_record)  # never change the caller's data
        origin, destination = record.get("origin_port", ""), record.get("destination_port", "")
        record.setdefault("route_id", f"{origin}-{destination}")
        for key, code in (("origin", origin), ("destination", destination)):
            record.setdefault(key, self._port_name(code))
        if not isinstance(record.get("sources"), list):
            record["sources"] = []
        record["risk_factors"], bad_factors = self._clean_list(record.get("risk_factors"), self.FACTOR_KEYS)
        record["insights"], bad_insights = self._clean_list(record.get("insights"), self.INSIGHT_KEYS)
        for insight in record["insights"]:
            try:
                insight["estimated_delay_days"] = max(0, int(insight["estimated_delay_days"]))
            except (TypeError, ValueError):
                insight["estimated_delay_days"] = 0
        record["_dropped_items"] = bad_factors + bad_insights
        return record

    def ensure_usable(self, record):
        missing = [f for f in self.REQUIRED_FIELDS if record.get(f) in (None, "")]
        if missing:
            raise InvalidRecordError(f"Validation failed: missing fields {missing}", "Incomplete AI record")
        conf = record.get("confidence_score")
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
            raise InvalidRecordError("Validation failed: confidence_score not in 0-1", "Invalid confidence score")

    @staticmethod
    def _port_name(code):
        port = validator.PORTS_BY_CODE.get(code)
        return port["name"] if port else str(code)

    @staticmethod
    def _clean_list(value, keys):
        if not isinstance(value, list):
            return [], 0
        good = [dict(item) for item in value if isinstance(item, dict) and all(k in item for k in keys)]
        return good, len(value) - len(good)
