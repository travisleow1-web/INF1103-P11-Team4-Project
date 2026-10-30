import json
from datetime import datetime
import operator

# Define a mapping from string representations to comparison functions


class DataManager:
  DB_FILE = "shipments.json"
  OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    "<":  operator.lt,
    "<=": operator.le,
    ">":  operator.gt,
    ">=": operator.ge,
  }
  records = []

  def __init__(self):
    self.records = self.load_csv()

  def load_csv(self):
    """Startup: load all records."""
    try:
      with open(self.DB_FILE, "r", encoding="utf-8") as f:
        print("Sucessfully loaded")
        return json.load(f)
    except FileNotFoundError:
      print("File Doesn't exist or is missing")
      return []
    except (json.JSONDecodeError, OSError):
      print("File is corrupted or another error occured")
      return []

  def save_records(self):
    """End of Program: save all records."""
    with open(self.DB_FILE, "w", encoding="utf-8") as f:
      json.dump(self.records, f, indent=2)

  def add_record(self, results):
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
        self.records.append(entry)
      except (OSError, TypeError) as exc:
        print(f"Warning: could not save {decision['shipment_id']}: {exc}")
    self.save_records()

  
  def get_route_history(self, route_id, since):
    """Used by Logic Manager Rule 3 (last 21 days on the same route)."""
    out = []
    for r in self.records:
      if r.get("route_id") != route_id:
        continue
      saved = datetime.fromisoformat(r["saved_at"])
      if saved >= since:
        out.append({"date": datetime.fromisoformat(r["saved_at"]), "flagged": r["flagged"], "delayed": r["delayed"]})
    return out

  def query_records(self, filter, opr):
    """Return the records matching every filter that is set; "" means not set."""

    #initialise empty records array
    filter_options = []
    for conditions in filter: # for each non-empty filter in filter, add it to filter options
      if filter.get(conditions) != "":
        filter_options.append(filter.get(conditions))
    if filter_options == []: # if no filters were added, return all records
      print("No Filters Used, Returning all Records")
      return self.records

    result = []
    for r in self.records:
      decision = r["decision"]

      #checks if filter is not empty, then checks if the record matches the record, records must match ALL filters
      for F in filter_options:
        if self.OPS[opr.get(F)](decision.get(F),filter.get(F)):
          break     
      else:
        result.append(r)
    if result == []:
      print("No Records found matching Filter")
    return result
