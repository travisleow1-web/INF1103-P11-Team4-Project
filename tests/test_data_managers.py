"""One set of tests run against every backend: they must behave the same (LSP)."""
import threading
from datetime import date, datetime, timezone
import pytest
from helpers import PORTS, ROTTERDAM, SINGAPORE, saved_record
from data_layer.json_data_manager import JsonDataManager
from data_layer.mongo_data_manager import MongoDataManager
from model.search_criteria import SearchCriteria
from model.storage_error import StorageError


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


# Damaged records

def store_with_a_damaged_record(kind, tmp_path):
    """A manager whose store holds SHP-001 (fine), a damaged SHP-002 and a non-object."""
    from data_layer.record_serializer import RecordSerializer
    good = RecordSerializer(PORTS).to_document(saved_record("SHP-001"))
    damaged = {**RecordSerializer(PORTS).to_document(saved_record("SHP-002")), "origin": "ZZZZZ"}
    if kind == "json":
        import json
        path = tmp_path / "records.json"
        path.write_text(json.dumps([good, damaged, "rubbish"]), encoding="utf-8")
        return JsonDataManager(path, PORTS)
    mongomock = pytest.importorskip("mongomock")
    collection = mongomock.MongoClient().db.records
    data = MongoDataManager(collection, PORTS)
    data.save(saved_record("SHP-001"))
    collection.insert_one(damaged)
    collection.insert_one({"note": "rubbish"})
    return data


@pytest.mark.parametrize("kind", ["json", "mongo"])
def test_a_damaged_record_is_skipped_and_logged(kind, tmp_path, caplog):
    data = store_with_a_damaged_record(kind, tmp_path)
    with caplog.at_level("WARNING"):
        assert ids(data.find(SearchCriteria())) == ["SHP-001"]
    assert "SHP-002" in caplog.text
    assert "position 2" in caplog.text


@pytest.mark.parametrize("kind", ["json", "mongo"])
def test_route_history_also_skips_damaged_records(kind, tmp_path):
    data = store_with_a_damaged_record(kind, tmp_path)
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert ids(data.find_route_history("SGSIN-NLRTM", since)) == ["SHP-001"]


# Route history (Logic Rule 3)

def at(day, hour=9):
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def test_route_history_is_empty_when_nothing_is_saved(data):
    assert data.find_route_history("SGSIN-NLRTM", at(1)) == []


def test_route_history_keeps_the_route_and_window_newest_first(data):
    data.save(saved_record("SHP-001", saved_at=at(1)))                      # too old
    data.save(saved_record("SHP-002", saved_at=at(10)))                     # exactly at since
    data.save(saved_record("SHP-003", saved_at=at(12)))
    data.save(saved_record("SHP-004", saved_at=at(11), origin=ROTTERDAM, destination=SINGAPORE))
    assert ids(data.find_route_history("SGSIN-NLRTM", at(10))) == ["SHP-003", "SHP-002"]
    assert ids(data.find_route_history("NLRTM-SGSIN", at(10))) == ["SHP-004"]


def test_route_history_skips_fallback_assessments(data):
    data.save(saved_record("SHP-001", saved_at=at(5), fallback=True))
    data.save(saved_record("SHP-002", saved_at=at(6), risk="HIGH", outcome="DELAY"))
    history = data.find_route_history("SGSIN-NLRTM", at(1))
    assert ids(history) == ["SHP-002"]
    assert history[0].is_flagged() and history[0].is_delayed()


def test_an_unknown_route_has_no_history(data):
    data.save(saved_record("SHP-001", saved_at=at(5)))
    assert data.find_route_history("SGSIN", at(1)) == []
    assert data.find_route_history("SGSIN-XXXXX", at(1)) == []


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


def test_route_history_from_a_corrupt_file_is_a_storage_error(tmp_path):
    path = tmp_path / "records.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StorageError):
        JsonDataManager(path, PORTS).find_route_history("SGSIN-NLRTM", datetime(2026, 11, 1, tzinfo=timezone.utc))


def run_in_threads(count, work):
    """Start count threads at once and return the errors they raised."""
    errors = []
    start = threading.Barrier(count)

    def run(number):
        start.wait()
        try:
            work(number)
        except Exception as error:          # collected and checked by the test
            errors.append(error)

    threads = [threading.Thread(target=run, args=(n,)) for n in range(1, count + 1)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return errors


def test_saves_from_many_threads_are_all_kept(tmp_path):
    data = JsonDataManager(tmp_path / "records.json", PORTS)
    errors = run_in_threads(20, lambda n: data.save(saved_record(f"SHP-{n:03d}")))
    assert errors == []
    assert sorted(ids(data.find(SearchCriteria()))) == [f"SHP-{n:03d}" for n in range(1, 21)]
    assert list(tmp_path.glob("*.tmp")) == []


def test_the_same_id_from_many_threads_is_saved_once(tmp_path):
    data = JsonDataManager(tmp_path / "records.json", PORTS)
    errors = run_in_threads(10, lambda n: data.save(saved_record("SHP-001")))
    assert len(errors) == 9 and all(isinstance(e, StorageError) for e in errors)
    assert ids(data.find(SearchCriteria())) == ["SHP-001"]


def test_records_survive_a_new_manager_on_the_same_file(tmp_path):
    path = tmp_path / "records.json"
    JsonDataManager(path, PORTS).save(saved_record("SHP-001"))
    assert ids(JsonDataManager(path, PORTS).find(SearchCriteria())) == ["SHP-001"]


# MongoDB connection

def test_connect_uses_the_shipment_records_collection(monkeypatch):
    mongomock = pytest.importorskip("mongomock")
    client = mongomock.MongoClient()
    monkeypatch.setattr("pymongo.MongoClient", lambda uri, **options: client)
    MongoDataManager.connect("mongodb://example", "team4", PORTS).save(saved_record("SHP-001"))
    assert client["team4"]["shipment_records"].count_documents({}) == 1


def test_connect_can_use_another_collection(monkeypatch):
    mongomock = pytest.importorskip("mongomock")
    client = mongomock.MongoClient()
    monkeypatch.setattr("pymongo.MongoClient", lambda uri, **options: client)
    MongoDataManager.connect("mongodb://example", "team4", PORTS, collection_name="test_records")
    assert "shipment_id_1" in client["team4"]["test_records"].index_information()


@pytest.mark.parametrize("uri, db_name", [
    ("http://not-a-mongo-address", "team4"),       # wrong scheme
    ("mongodb://localhost:99999", "team4"),        # port out of range (ValueError in the driver)
    ("mongodb://localhost:27017", "team 4"),       # invalid database name (InvalidName)
])
def test_bad_connection_settings_are_a_short_storage_error(uri, db_name):
    # each of these fails before any network call
    with pytest.raises(StorageError, match="^Database unavailable. Results will not be saved.$"):
        MongoDataManager.connect(uri, db_name, PORTS)
