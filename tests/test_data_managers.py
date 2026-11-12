"""One set of tests run against every backend: they must behave the same (LSP)."""
from datetime import date, datetime, timezone
import pytest
from helpers import PORTS, saved_record
from data_layer.json_data_manager import JsonDataManager
from data_layer.mongo_data_manager import MongoDataManager
from io_layer.search_criteria import SearchCriteria
from io_layer.storage_error import StorageError


@pytest.fixture(params=["json", "mongo"])
def data(request, tmp_path):
    if request.param == "json":
        return JsonDataManager(tmp_path / "records.json", PORTS)
    mongomock = pytest.importorskip("mongomock")
    return MongoDataManager(mongomock.MongoClient().db.records, PORTS)


def ids(records):
    return [r.shipment.shipment_id for r in records]


def test_nothing_saved_finds_nothing(data):
    assert data.find(SearchCriteria()) == []


def test_no_filters_returns_everything_newest_first(data):
    data.save(saved_record("SHP-001", saved_at=datetime(2026, 11, 1, 9, tzinfo=timezone.utc)))
    data.save(saved_record("SHP-003", saved_at=datetime(2026, 11, 3, 9, tzinfo=timezone.utc)))
    data.save(saved_record("SHP-002", saved_at=datetime(2026, 11, 2, 9, tzinfo=timezone.utc)))
    assert ids(data.find(SearchCriteria())) == ["SHP-003", "SHP-002", "SHP-001"]


def test_a_saved_record_comes_back_whole(data):
    original = saved_record("SHP-001", risk="HIGH", needs_human=True, fallback=True)
    data.save(original)
    found = data.find(SearchCriteria())[0]
    assert found.shipment == original.shipment             # dates come back as real dates
    assert found.assessment.is_fallback()
    assert found.decision.to_dict() == original.decision.to_dict()


def test_filters_on_the_decision_fields(data):
    data.save(saved_record("SHP-001", risk="LOW", outcome="PROCEED"))
    data.save(saved_record("SHP-002", risk="HIGH", outcome="ESCALATE", needs_human=True))
    assert ids(data.find(SearchCriteria(overall_risk="HIGH"))) == ["SHP-002"]
    assert ids(data.find(SearchCriteria(outcome="PROCEED"))) == ["SHP-001"]
    assert ids(data.find(SearchCriteria(needs_human=True))) == ["SHP-002"]
    assert ids(data.find(SearchCriteria(needs_human=False))) == ["SHP-001"]


def test_risk_filter_ignores_case(data):
    data.save(saved_record("SHP-001", risk="Low"))
    assert ids(data.find(SearchCriteria(overall_risk="LOW"))) == ["SHP-001"]


def test_filters_on_id_and_ports(data):
    data.save(saved_record("SHP-001"))
    assert ids(data.find(SearchCriteria(shipment_id="SHP-001", origin="SGSIN", destination="NLRTM"))) == ["SHP-001"]
    assert data.find(SearchCriteria(shipment_id="SHP-009")) == []
    assert data.find(SearchCriteria(origin="NLRTM")) == []


def test_departure_range_is_inclusive_at_both_ends(data):
    for number, day in enumerate([9, 10, 15, 20, 21], start=1):
        data.save(saved_record(f"SHP-00{number}", departure=date(2026, 12, day)))
    found = data.find(SearchCriteria(departure_from=date(2026, 12, 10), departure_to=date(2026, 12, 20)))
    assert sorted(ids(found)) == ["SHP-002", "SHP-003", "SHP-004"]


def test_filters_combine(data):
    data.save(saved_record("SHP-001", risk="HIGH", departure=date(2026, 12, 1)))
    data.save(saved_record("SHP-002", risk="HIGH", departure=date(2027, 1, 1)))
    data.save(saved_record("SHP-003", risk="LOW", departure=date(2026, 12, 1)))
    found = data.find(SearchCriteria(overall_risk="HIGH", departure_to=date(2026, 12, 31)))
    assert ids(found) == ["SHP-001"]


def test_saving_the_same_shipment_id_twice_is_an_error(data):
    data.save(saved_record("SHP-001"))
    with pytest.raises(StorageError, match="already saved"):
        data.save(saved_record("SHP-001"))
    assert len(data.find(SearchCriteria())) == 1


# JSON file problems

def test_a_missing_file_is_empty_and_is_created_on_save(tmp_path):
    path = tmp_path / "new.json"
    data = JsonDataManager(path, PORTS)
    assert data.find(SearchCriteria()) == []
    data.save(saved_record())
    assert path.exists()


def test_a_corrupt_file_is_a_storage_error_and_is_not_overwritten(tmp_path):
    path = tmp_path / "records.json"
    path.write_text("{not json", encoding="utf-8")
    data = JsonDataManager(path, PORTS)
    with pytest.raises(StorageError):
        data.find(SearchCriteria())
    with pytest.raises(StorageError):
        data.save(saved_record())
    assert path.read_text(encoding="utf-8") == "{not json"


def test_a_file_that_is_not_a_list_is_a_storage_error(tmp_path):
    path = tmp_path / "records.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(StorageError):
        JsonDataManager(path, PORTS).find(SearchCriteria())


def test_records_survive_a_new_manager_on_the_same_file(tmp_path):
    path = tmp_path / "records.json"
    JsonDataManager(path, PORTS).save(saved_record("SHP-001"))
    assert ids(JsonDataManager(path, PORTS).find(SearchCriteria())) == ["SHP-001"]
