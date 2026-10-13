import json
import os
from datetime import UTC, datetime

# Loaded once at import. The path is relative, so run from the repo root.
with open("ports_reference_4.json") as f:
    PORTS = json.load(f)["ports"]

# Autocomplete entries shown to the user, e.g. "<code> - <name>, <country>".
PORT_CHOICES = [f"{p['code']} - {p['name']}, {p['country']}" for p in PORTS]
# Lookup table from port code to its full reference record.
PORTS_BY_CODE = {p["code"]: p for p in PORTS}


def port_coordinates(code):
    """Return (lat, lon) for a port code. Raises KeyError for an unknown code, so only pass validated codes."""
    port = PORTS_BY_CODE[code]
    return port["lat"], port["lon"]


def validate_date(text):
    """Questionary validator: True for a DD/MM/YYYY date, otherwise an error message."""
    value = text.strip()
    if value == "":
        return "Departure time is required."
    # Rejects wrong formats and impossible dates such as 31/02/2026.
    try:
        datetime.strptime(value, "%d/%m/%Y").replace(tzinfo=UTC)
    except ValueError:
        return "Use DD/MM/YYYY , e.g. 01/01/2026"
    return True


def validate_arrival_date(text, departure):
    """Questionary validator: a valid DD/MM/YYYY date after the departure string."""
    result = validate_date(text)
    if result is not True:
        return result
    if datetime.strptime(text.strip(), "%d/%m/%Y") <= datetime.strptime(departure, "%d/%m/%Y"):
        return "Arrival must be after the departure date."
    return True


def validate_port(answer):
    """Questionary validator: the answer must be exactly one of PORT_CHOICES."""
    if answer in PORT_CHOICES:
        return True
    return "Unknown port, pick one from the list"


def validate_destination_port(answer, origin):
    """Questionary validator: a known port that differs from the origin port code."""
    result = validate_port(answer)
    if result is not True:
        return result
    if answer.split(" - ")[0].strip().upper() == origin:
        return "Destination must be different from the origin port."
    return True


def validate_csv_path(text):
    """Questionary validator: a path to an existing .csv file."""
    value = text.strip()
    if value == "":
        return "File path is required."
    if not value.lower().endswith(".csv"):
        return "File must be a .csv file."
    if not os.path.isfile(value):
        return "File not found."
    return True