import json
import logging
import os
from datetime import datetime

DB_FILE = "shipments.json"

def load_records(file_path):
    """Startup: load all records."""
    with open(file_path, "r", encoding="utf-8") as f:
      return json.load(f)
