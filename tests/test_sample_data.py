from pathlib import Path
import pytest
from io_layer.csv_source import CsvSource
from io_layer.shipment_validator import ShipmentValidator
from model.port_registry import PortRegistry

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def check_every_row(name):
    validator = ShipmentValidator(PortRegistry.from_json())
    rows = CsvSource((SAMPLE_DIR / name).read_bytes()).read()
    results = [validator.check(row, f"SHP-{number:03d}") for number, row in enumerate(rows, 1)]
    return rows, [error for result in results for error in result.errors]


@pytest.mark.parametrize("name", ["shipments.csv", "shipments_live.csv"])
def test_sample_csv_is_valid(name):
    rows, errors = check_every_row(name)
    assert rows and errors == []


def test_live_sample_has_mostly_short_routes_that_fit_the_forecast():
    rows, _ = check_every_row("shipments_live.csv")
    validator = ShipmentValidator(PortRegistry.from_json())
    days = [(validator.read_date(r["arrival_time"]) - validator.read_date(r["departure_time"])).days for r in rows]
    assert sum(1 for d in days if d <= 7) >= 10               # the rows that can get a suggestion
    assert any(d > 16 for d in days)                          # and one long voyage that cannot
