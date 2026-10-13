import json
import logging
import os
from datetime import datetime

DB_FILE = "shipments.json"

def load_records(file_path):
    """Startup: load all records."""
    try:
      with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
    except FileNotFoundError: #File Doesn't exist or is missing
      return []
    except (json.JSONDecodeError, OSError) as exc: #File is corrupted or any other errors
      return []

def save_records(db_records, file_path):
  """End of Program: save all records."""
  with open(file_path, "w", encoding="utf-8") as f:
    json.dump(db_records, f, indent=2)

def add_record(file_path, db_records, record, decision):
  """decision is a dict. Stores both, plus fields used for history look-ups."""

  entry = {
    **record,
    "decision": decision,
    "saved_at": datetime.now().isoformat(),
    "flagged": decision["needs_human"] or decision["overall_risk"] != "Low",
    "delayed": decision["outcome"] == "DELAY",
  }
  db_records.append(json.loads(json.dumps(entry, default=str)))
  save_records(db_records, file_path)

def get_route_history(db_records, route_id, since):
  """Used by Logic Manager Rule 3 (last 21 days on the same route)."""
  out = []
  for r in db_records:
    if r.get("route_id") != route_id:
      continue
    saved = datetime.fromisoformat(r["saved_at"])
    if saved >= since:
      out.append({"date": saved, "flagged": r["flagged"], "delayed": r["delayed"]})
  return out

def query_records(db_records, filter):
  """Used by IO Manager filter/query."""
  risk = filter.get("risk")
  outcome = filter.get("outcome")
  needs_human = filter.get("needs_human")
  text = filter.get("text")
  text_lower = text.lower() if text else None

  # Fast-path: if no filters applied, return shallow full list
  if not (risk or outcome or (needs_human is not None) or text_lower):
    return db_records

  result = []
  for r in db_records:
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
