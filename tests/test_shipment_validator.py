from datetime import date
from helpers import PORTS, row
from io_layer.shipment_validator import ShipmentValidator


def check(**changes):
    return ShipmentValidator(PORTS).check(row(**changes), "SHP-001")


def test_valid_row_builds_a_shipment():
    result = check()
    assert result.is_valid()
    assert result.shipment.shipment_id == "SHP-001"
    assert result.shipment.departure == date(2026, 12, 1)


def test_port_label_is_accepted():
    assert check(origin_port="SGSIN - Singapore, SG").is_valid()


def test_values_are_trimmed():
    assert check(origin_port=" sgsin ", departure_time=" 01/12/2026 ").is_valid()


def test_unknown_port():
    assert check(origin_port="XXXXX").errors == ["Origin: unknown port 'XXXXX'"]


def test_same_port():
    assert check(destination_port="SGSIN").errors == ["Origin and destination are the same port"]


def test_arrival_must_be_after_departure():
    assert check(arrival_time="01/12/2026").errors == ["Arrival must be after departure"]


def test_impossible_date():
    assert check(departure_time="31/02/2026").errors == [
        "Departure: '31/02/2026' is not a valid date (use DD/MM/YYYY)"]


def test_only_dd_mm_yyyy_is_accepted():
    assert "Departure" in check(departure_time="2026-12-01").errors[0]


def test_all_missing_fields_are_reported_together():
    assert check(origin_port="", arrival_time="").errors == ["Origin port is missing",
                                                              "Arrival date is missing"]


def test_fields_that_are_present_are_still_checked_when_another_is_missing():
    assert check(destination_port="", origin_port="XXXXX", departure_time="2026-12-01").errors == [
        "Origin: unknown port 'XXXXX'",
        "Destination port is missing",
        "Departure: '2026-12-01' is not a valid date (use DD/MM/YYYY)",
    ]


def test_cross_field_checks_need_both_sides_valid():
    assert check(departure_time="bad", arrival_time="01/01/2020").errors == [
        "Departure: 'bad' is not a valid date (use DD/MM/YYYY)"]
    assert check(origin_port="", destination_port="SGSIN").errors == ["Origin port is missing"]


def test_a_none_value_counts_as_missing():
    assert check(arrival_time=None).errors == ["Arrival date is missing"]


def test_an_absent_column_counts_as_missing():
    incomplete = row()
    del incomplete["arrival_time"]
    assert ShipmentValidator(PORTS).check(incomplete, "SHP-001").errors == ["Arrival date is missing"]


def test_errors_cannot_be_changed_from_outside():
    result = check(origin_port="XXXXX")
    result.errors.clear()
    assert len(result.errors) == 1


def test_read_date():
    validator = ShipmentValidator(PORTS)
    assert validator.read_date("05/12/2026") == date(2026, 12, 5)
    assert validator.read_date("2026-12-05") is None
