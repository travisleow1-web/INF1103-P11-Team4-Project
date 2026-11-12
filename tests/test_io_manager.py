from datetime import date
from helpers import FakeData, make_io, record, row
from io_layer.form_source import FormSource
from model.search_criteria import SearchCriteria
from model.storage_error import StorageError


def ids(preview):
    return [s.shipment_id for s in preview.valid_shipments()]


# preview

def test_ids_continue_from_saved_records():
    preview = make_io(FakeData([record("SHP-007")])).preview(FormSource(row()), FormSource(row()))
    assert ids(preview) == ["SHP-008", "SHP-009"]


def test_ids_start_at_one_when_nothing_is_saved():
    assert ids(make_io().preview(FormSource(row()))) == ["SHP-001"]


def test_saved_ids_that_are_not_numbered_are_ignored():
    preview = make_io(FakeData([record("ABC-1"), record("SHP-004")])).preview(FormSource(row()))
    assert ids(preview) == ["SHP-005"]


def test_ids_start_at_one_when_storage_fails():
    data = FakeData(error=StorageError("db down"))
    assert ids(make_io(data).preview(FormSource(row()))) == ["SHP-001"]


def test_a_shipment_id_column_is_ignored():
    assert ids(make_io().preview(FormSource(row(shipment_id="ABC-1")))) == ["SHP-001"]


def test_invalid_rows_do_not_use_up_numbers():
    preview = make_io().preview(FormSource(row(origin_port="XXXXX")), FormSource(row()))
    assert ids(preview) == ["SHP-001"]


def test_preview_separates_valid_and_problem_rows():
    preview = make_io().preview(FormSource(row()), FormSource(row(origin_port="XXXXX")))
    assert preview.total() == 2
    assert len(preview.valid_shipments()) == 1
    assert preview.has_problems()
    assert preview.problems()[0][0] == 2


# search

def test_search_builds_criteria_from_the_form():
    data = FakeData()
    make_io(data).search({"origin": "SGSIN - Singapore, SG", "destination": "",
                          "departure_from": "01/12/2026", "departure_to": "31/12/2026",
                          "needs_human": "yes", "overall_risk": "High"})
    criteria = data.last_criteria
    assert criteria.origin == "SGSIN"
    assert criteria.destination is None
    assert criteria.departure_from == date(2026, 12, 1)
    assert criteria.departure_to == date(2026, 12, 31)
    assert criteria.needs_human is True
    assert criteria.overall_risk == "High"


def test_search_with_no_filters_asks_for_everything():
    data = FakeData()
    make_io(data).search({})
    assert data.last_criteria.to_dict() == {}


def test_needs_human_no_is_kept_and_blank_means_any():
    data = FakeData()
    make_io(data).search({"needs_human": "no"})
    assert data.last_criteria.needs_human is False
    make_io(data).search({"needs_human": ""})
    assert data.last_criteria.needs_human is None


def test_from_date_after_to_date_is_an_error():
    data = FakeData()
    result = make_io(data).search({"departure_from": "31/12/2026", "departure_to": "01/12/2026"})
    assert result["kind"] == "error"
    assert data.last_criteria is None            # nothing was searched


def test_bad_date_and_unknown_port_are_both_reported():
    result = make_io().search({"origin": "XXXXX", "departure_from": "2026-12-01"})
    assert result["kind"] == "error"
    assert "origin" in result["message"] and "from date" in result["message"]


def test_search_shipment_id_is_upper_cased():
    data = FakeData()
    make_io(data).search({"shipment_id": " shp-001 "})
    assert data.last_criteria.shipment_id == "SHP-001"


def test_search_returns_a_summary_and_details_for_each_record():
    result = make_io(FakeData([record("SHP-001"), record("SHP-002")])).search({})
    assert result["kind"] == "results"
    assert [r["shipment_id"] for r in result["summary"]] == ["SHP-001", "SHP-002"]
    assert [r["shipment_id"] for r in result["records"]] == ["SHP-001", "SHP-002"]


def test_search_with_no_matches_says_so():
    assert make_io().search({"shipment_id": "SHP-009"}) == {"kind": "empty", "message": "No records match."}


def test_a_storage_failure_is_shown_not_raised():
    result = make_io(FakeData(error=StorageError("db down"))).search({})
    assert result == {"kind": "error", "message": "db down"}


# display data

def test_show_result_uses_dd_mm_yyyy_and_the_port_label():
    shown = make_io().show_result(record())
    assert shown["departure"] == "01/12/2026"
    assert shown["origin"] == "SGSIN - Singapore, SG"
    assert shown["decision"]["outcome"] == "PROCEED"


def test_show_summary_has_the_columns_the_old_cli_showed():
    row_ = make_io().show_summary([record()])[0]
    assert row_["route"] == "SGSIN -> NLRTM"
    assert row_["expected_impact"] == "minor_delay"
    assert row_["confidence_score"] == 0.8
    assert row_["primary_factor"] == "WEATHER"
    assert row_["primary_severity"] == "MEDIUM"
    assert row_["n_risk_factors"] == 2
    assert row_["conflicting_sources"] is False
    assert row_["outcome"] == "PROCEED"


def test_show_summary_flags_shipments_the_ai_did_not_assess():
    rows = make_io().show_summary([record("SHP-001"), record("SHP-002", fallback=True)])
    assert [r["ai_unavailable"] for r in rows] == [False, True]


def test_show_input_form_lists_the_ports():
    assert make_io().show_input_form()["ports"] == ["SGSIN - Singapore, SG", "NLRTM - Rotterdam, NL"]


def test_search_criteria_to_dict_keeps_false_but_drops_blanks():
    assert SearchCriteria(needs_human=False, outcome="").to_dict() == {"needs_human": False}
