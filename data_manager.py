import json
from datetime import datetime

DB_FILE = "shipments.json"

def load_records(file_path):
    """Startup: load all records."""
    try:
      with open(file_path, "r", encoding="utf-8") as f:
        print("Sucessfully loaded")
        return json.load(f)
    except FileNotFoundError:
      print("File Doesn't exist or is missing")
      return []
    except (json.JSONDecodeError, OSError):
      print("File is corrupted or another error occured")
      return []

def save_records(db_records, file_path):
  """End of Program: save all records."""
  with open(file_path, "w", encoding="utf-8") as f:
    json.dump(db_records, f, indent=2)

def add_record(file_path, db_records, results):
  """Append each (record, decision) pair to db_records with its history fields, then save."""
  for record, decision in results:
    try:
      entry = {
        **record,
        "decision": decision,
        "saved_at": datetime.now().isoformat(),
        "flagged": decision["needs_human"] or decision["overall_risk"] != "Low",
        "delayed": decision["outcome"] == "DELAY",
      }
      db_records.append(json.loads(json.dumps(entry, default=str)))
    except (OSError, TypeError) as exc:
      print(f"Warning: could not save {decision['shipment_id']}: {exc}")
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
  """Return the records matching every filter that is set; "" means not set."""

  
  risk = filter.get("risk")
  outcome = filter.get("outcome")
  needs_human = filter.get("needs_human")

  # No filters set: return everything
  if risk == "" and outcome == "" and needs_human == "":
    print("No Filters Used, Returning all Records")
    return db_records
  print("Filters Used, Returning Records")
  result = []
  for r in db_records:
    decision = r["decision"]

    # A filter left as "" was never set, so it matches every record.
    if risk != "" and decision.get("overall_risk") != risk:
      continue
    if outcome != "" and decision.get("outcome") != outcome:
      continue
    if needs_human != "" and decision.get("needs_human") != needs_human:
      continue
    result.append(r)

  return result
