from helpers import PORTS, make_io, row
from fakes import FakeAI, FakeLogic
from data_layer.json_data_manager import JsonDataManager
from io_layer.form_source import FormSource
from io_layer.search_criteria import SearchCriteria
from main import assess_shipments


def shipments(io, count):
    return io.preview(*[FormSource(row()) for _ in range(count)]).valid_shipments()


def test_each_shipment_is_saved_as_it_is_yielded(tmp_path):
    data = JsonDataManager(tmp_path / "records.json", PORTS)
    stream = assess_shipments(shipments(make_io(data), 3), FakeAI(), FakeLogic(), data)
    next(stream)
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
