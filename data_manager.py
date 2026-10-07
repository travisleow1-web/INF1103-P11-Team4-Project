import json
import logging
import os
from datetime import datetime

log = logging.getLogger("data_manager")
DB_FILE = "shipments.json"



class DataManager:
    def __init__(self, path=DB_FILE):
        self.path = path
        self.records = []
        self._load()

    def _load(self):
        """Startup: load all records. Missing or corrupt file -> start empty + log."""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.records = json.load(f)
        except FileNotFoundError: #File Doesn't exist or is missing
            self.records = []
        except (json.JSONDecodeError, OSError) as exc: #File is corrupted or any other errors
            log.error("Could not read %s (%s). Starting with an empty dataset.", self.path, exc)
            self.records = []

    def save_record(self, record, decision):
        """decision is a dict. Stores both, plus fields used for history look-ups."""
        entry = {
            **record,
            "decision": decision,
            "saved_at": datetime.now().isoformat(),
            "flagged": decision["needs_human"] or decision["overall_risk"] != "Low",
            "delayed": decision["outcome"] == "DELAY",
        }
        self.records.append(json.loads(json.dumps(entry, default=str)))
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, indent=2)

    def get_route_history(self, route_id, since):
        """Used by Logic Manager Rule 3 (last 21 days on the same route)."""
        out = []
        for r in self.records:
            if r.get("route_id") != route_id:
                continue
            saved = datetime.fromisoformat(r["saved_at"])
            if saved >= since:
                out.append({"date": saved, "flagged": r["flagged"], "delayed": r["delayed"]})
        return out

    def query_records(self, filter):
        """Used by IO Manager filter/query."""
        risk = filter.get("risk")
        outcome = filter.get("outcome")
        needs_human = filter.get("needs_human")
        text = filter.get("text")
        text_lower = text.lower() if text else None

        # Fast-path: if no filters applied, return shallow full list
        if not (risk or outcome or (needs_human is not None) or text_lower):
            return self.records

        result = []
        for r in self.records:
            decision = r["decision"]

            matched_record = (
                #filtered criteria is not empty and record matches criteria
                (risk and decision.get("overall_risk") == risk) or 
                (outcome and decision.get("outcome") == outcome) or 
                (needs_human is not None and decision.get("needs_human") == needs_human) or
                (text_lower and (text_lower in r["origin"].lower() or text_lower in r["destination"].lower()))
            )
            if matched_record:
                result.append(r)

        return result