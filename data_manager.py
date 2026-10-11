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



records = load_records(DB_FILE)
