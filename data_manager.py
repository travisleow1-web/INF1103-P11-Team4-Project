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

records = load_records(DB_FILE)
