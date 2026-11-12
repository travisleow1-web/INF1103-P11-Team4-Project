from helpers import PORTS, make_io, row
from fakes import FakeAI, FakeLogic
from data_layer.json_data_manager import JsonDataManager
from data_layer.unavailable_data_manager import UnavailableDataManager
from io_layer.form_source import FormSource
from model.search_criteria import SearchCriteria
from model.shipment_record import ShipmentRecord
from main import assess_shipments


def shipments(io, count):
    return io.preview(*[FormSource(row()) for _ in range(count)]).valid_shipments()


def test_each_shipment_is_saved_as_it_is_yielded(tmp_path):
    data = JsonDataManager(tmp_path / "records.json", PORTS)
    stream = assess_shipments(shipments(make_io(data), 3), FakeAI(), FakeLogic(), data)
    record, save_error = next(stream)
    assert isinstance(record, ShipmentRecord) and save_error is None
    assert len(data.find(SearchCriteria())) == 1           # one done, the rest not started
    assert len(list(stream)) == 2
    assert len(data.find(SearchCriteria())) == 3


def test_the_flow_works_end_to_end_with_the_real_io_and_data_layers(tmp_path):
    data = JsonDataManager(tmp_path / "records.json", PORTS)
    io = make_io(data)
    list(assess_shipments(shipments(io, 3), FakeAI(), FakeLogic(), data))

    assert [s.shipment_id for s in io.preview(FormSource(row())).valid_shipments()] == ["SHP-004"]

    result = io.search({"overall_risk": "high"})
    assert result["kind"] == "results"
    assert [r["shipment_id"] for r in result["summary"]] == ["SHP-002"]
    assert result["records"][0]["departure"] == "01/12/2026"
    assert io.search({"shipment_id": "SHP-009"})["kind"] == "empty"


def test_a_failed_save_is_reported_and_the_rest_still_run():
    data = UnavailableDataManager("Database is down")
    results = list(assess_shipments(shipments(make_io(data), 3), FakeAI(), FakeLogic(), data))
    assert [r.shipment.shipment_id for r, _ in results] == ["SHP-001", "SHP-002", "SHP-003"]
    assert [error for _, error in results] == ["Database is down"] * 3


def test_only_the_shipment_that_failed_is_marked_not_saved(tmp_path):
    data = JsonDataManager(tmp_path / "records.json", PORTS)
    io = make_io(data)
    first = shipments(io, 2)
    list(assess_shipments(first[:1], FakeAI(), FakeLogic(), data))     # SHP-001 is saved already
    results = list(assess_shipments(first, FakeAI(), FakeLogic(), data))
    assert results[0][1] == "SHP-001 is already saved"
    assert results[1][1] is None
    assert len(data.find(SearchCriteria())) == 2
