import json
from datetime import date
from ai_helpers import make_shipment, valid_raw
from ai_layer.response_cache import ResponseCache
from helpers import SINGAPORE
from model.shipment import Shipment

TODAY = date(2026, 11, 13)


def test_key_ignores_the_shipment_id():
    cache = ResponseCache("unused.json", "v1")
    assert cache.make_key(make_shipment("SHP-001"), TODAY) == cache.make_key(make_shipment("SHP-999"), TODAY)


def test_key_changes_with_route_dates_day_and_version():
    cache = ResponseCache("unused.json", "v1")
    base = cache.make_key(make_shipment(), TODAY)
    reverse = make_shipment()
    reverse = Shipment("SHP-001", reverse.destination, SINGAPORE, reverse.departure, reverse.arrival)
    assert cache.make_key(reverse, TODAY) != base
    assert cache.make_key(make_shipment(departure=date(2026, 12, 2)), TODAY) != base
    assert cache.make_key(make_shipment(arrival=date(2026, 12, 21)), TODAY) != base
    assert cache.make_key(make_shipment(), date(2026, 11, 14)) != base
    assert ResponseCache("unused.json", "v2").make_key(make_shipment(), TODAY) != base


def test_key_defaults_to_the_utc_day():
    cache = ResponseCache("unused.json", "v1")
    assert len(cache.make_key(make_shipment())) == 64


def test_set_then_get_survives_a_new_instance(tmp_path):
    path = tmp_path / "ai_cache.json"
    ResponseCache(path, "v1").set("k", valid_raw(), "2026-11-13T02:00:00+00:00")
    entry = ResponseCache(path, "v1").get("k")
    assert entry == {"result": valid_raw(), "fetched_at": "2026-11-13T02:00:00+00:00"}
    assert not (tmp_path / "ai_cache.json.tmp").exists()


def test_missing_file_is_empty(tmp_path):
    assert ResponseCache(tmp_path / "none.json", "v1").get("k") is None


def test_unreadable_file_is_empty_and_is_replaced_on_write(tmp_path):
    path = tmp_path / "ai_cache.json"
    path.write_text("{broken", encoding="utf-8")
    cache = ResponseCache(path, "v1")
    assert cache.get("k") is None
    cache.set("k", valid_raw(), "2026-11-13T02:00:00+00:00")
    assert json.loads(path.read_text(encoding="utf-8"))["k"]["result"] == valid_raw()


def test_file_that_is_not_an_object_is_empty(tmp_path):
    path = tmp_path / "ai_cache.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert ResponseCache(path, "v1").get("k") is None


def test_write_failure_is_logged_not_raised(tmp_path, caplog):
    cache = ResponseCache(tmp_path / "no_such_dir" / "ai_cache.json", "v1")
    cache.set("k", valid_raw(), "2026-11-13T02:00:00+00:00")
    assert cache.get("k") is not None          # still served from memory
    assert "Could not write AI cache" in caplog.text
