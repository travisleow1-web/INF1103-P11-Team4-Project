"""Web pages through FastAPI's TestClient, with a temp-file JSON data manager. No network."""
import json
import logging
import threading
from unittest.mock import patch
import pytest
import requests
from fastapi.testclient import TestClient
from ai_helpers import gemini_reply, make_shipment, valid_raw
from helpers import PORTS, make_io, saved_record
from fakes import FakeAI, FakeLogic
from data_layer.json_data_manager import JsonDataManager
from data_layer.unavailable_data_manager import UnavailableDataManager
from model.search_criteria import SearchCriteria
from model.storage_error import StorageError
from web.app import MAX_UPLOAD_BYTES, create_web_app
import main

CSV = b"origin_port,destination_port,departure_time,arrival_time\nSGSIN,NLRTM,01/12/2026,20/12/2026\n"


def good_rows(count):
    return {"origin_port": ["SGSIN"] * count, "destination_port": ["NLRTM"] * count,
            "departure_time": ["01/12/2026"] * count, "arrival_time": ["20/12/2026"] * count}


@pytest.fixture
def data(tmp_path):
    return JsonDataManager(tmp_path / "records.json", PORTS)


def client_for(data, ai=None, logic=None, demo=False, notices=None):
    return TestClient(create_web_app(make_io(data), ai, logic, data, demo, notices, run=main.assess_shipments))


# input page

def test_input_page_lists_the_ports_and_labels_every_box(data):
    page = client_for(data).get("/")
    assert page.status_code == 200
    assert '<option value="SGSIN - Singapore, SG">' in page.text
    assert page.text.count('placeholder="DD/MM/YYYY"') == 2
    assert page.text.count('<span class="sr-only">') == 4
    assert 'id="add-row"' in page.text
    assert "Demo mode" not in page.text
    assert "banner-error" not in page.text


def test_static_files_are_served(data):
    client = client_for(data)
    assert client.get("/static/style.css").status_code == 200
    assert "add-row" in client.get("/static/add_row.js").text


# submit without AI and Logic

def test_valid_rows_without_ai_say_not_connected_and_stay_filled(data):
    rows = good_rows(2)
    rows["origin_port"][1] = "SGSIN - Singapore, SG"
    page = client_for(data).post("/submit", data=rows)
    assert page.status_code == 200
    assert "2 shipments are valid. AI and Logic are not connected yet." in page.text
    assert page.text.count("not connected yet") == 1                   # no second notice
    assert page.text.count('name="origin_port"') == 2
    assert 'value="SGSIN - Singapore, SG"' in page.text


def test_the_home_page_says_up_front_when_ai_and_logic_are_not_connected(data):
    assert "AI and Logic are not connected yet." in client_for(data).get("/").text
    assert "not connected" not in demo_client(data).get("/").text


NO_AI = "AI is not connected: set GEMINI_API_KEY in .env (or start with DEMO_MODE=1)."


def test_without_only_the_ai_the_pages_say_how_to_connect_it(data):
    client = client_for(data, logic=FakeLogic())
    home = client.get("/").text
    assert NO_AI in home and "AI and Logic" not in home
    page = client.post("/submit", data=good_rows(1)).text
    assert f"1 shipment is valid. {NO_AI}" in page
    assert page.count("not connected") == 1


def test_without_only_the_logic_the_pages_say_so(data):
    page = client_for(data, ai=FakeAI()).post("/submit", data=good_rows(1)).text
    assert "1 shipment is valid. Logic is not connected yet." in page


def test_blank_typed_rows_are_skipped(data):
    rows = good_rows(1)
    for values in rows.values():
        values.append("")
    page = client_for(data).post("/submit", data=rows)
    assert "1 shipment is valid." in page.text


def test_invalid_rows_show_every_error_and_keep_what_was_typed(data):
    rows = good_rows(2)
    rows["origin_port"][1] = "XXXXX"
    rows["arrival_time"][1] = "2026-12-20"
    page = client_for(data).post("/submit", data=rows)
    assert page.status_code == 422
    assert "Nothing was assessed" in page.text
    assert "Row 2: Origin: unknown port &#39;XXXXX&#39;; Arrival: &#39;2026-12-20&#39; is not a valid date" in page.text
    assert 'value="XXXXX"' in page.text
    assert "shipments are valid" not in page.text


def test_typed_rows_with_errors_are_marked_for_screen_readers(data):
    rows = good_rows(2)
    rows["origin_port"][1] = "XXXXX"
    rows["destination_port"][1] = ""
    page = client_for(data).post("/submit", data=rows, files={"csv_file": ("s.csv", CSV, "text/csv")})
    text = page.text
    assert text.count('<tr class="entry has-errors">') == 1
    assert text.count('aria-invalid="true" aria-describedby="row-2-errors"') == 4
    # the CSV row is row 1, so the second typed row is row 3
    assert ('<td colspan="4" id="row-2-errors">Row 3: Origin: unknown port &#39;XXXXX&#39;; '
            'Destination port is missing</td>') in text


def test_user_text_is_escaped(data):
    rows = good_rows(1)
    rows["origin_port"] = ["<script>alert(1)</script>"]
    page = client_for(data).post("/submit", data=rows)
    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;" in page.text


def test_nothing_to_submit_is_an_error(data):
    page = client_for(data).post("/submit", data={"origin_port": [""], "destination_port": [""]})
    assert page.status_code == 400
    assert "Add at least one shipment" in page.text


def test_csv_upload_is_read_together_with_typed_rows(data):
    page = client_for(data).post("/submit", data=good_rows(1),
                                 files={"csv_file": ("shipments.csv", CSV, "text/csv")})
    assert "2 shipments are valid." in page.text


def test_an_empty_file_box_is_ignored(data):
    page = client_for(data).post("/submit", data=good_rows(1),
                                 files={"csv_file": ("", b"", "application/octet-stream")})
    assert "1 shipment is valid." in page.text


def test_an_unreadable_csv_shows_the_reason(data):
    page = client_for(data).post("/submit", files={"csv_file": ("x.csv", CSV.splitlines()[0], "text/csv")})
    assert page.status_code == 400
    assert "The file has no shipments." in page.text


def test_an_oversized_request_is_refused_before_the_form_is_read(data):
    # Not valid multipart: reading it would fail, so a 413 shows the size check ran first.
    page = client_for(data).post("/submit", content=b"x" * (2 * MAX_UPLOAD_BYTES),
                                 headers={"content-type": "multipart/form-data; boundary=nothing"})
    assert page.status_code == 413
    assert "larger than 1 MB" in page.text


def test_a_file_of_exactly_1_mb_is_accepted(data):
    line = b"SGSIN,NLRTM,01/12/2026,20/12/2026\n"
    header = CSV.splitlines(keepends=True)[0]
    body = header + line * ((MAX_UPLOAD_BYTES - len(header)) // len(line))
    body += b" " * (MAX_UPLOAD_BYTES - len(body) - 1) + b"\n"           # pad to exactly 1 MB
    assert len(body) == MAX_UPLOAD_BYTES
    page = client_for(data).post("/submit", files={"csv_file": ("big.csv", body, "text/csv")})
    assert page.status_code != 413


def test_a_csv_with_wrong_columns_says_which_are_missing(data):
    page = client_for(data).post("/submit", files={"csv_file": ("x.csv", b"from,to\nSGSIN,NLRTM\n", "text/csv")})
    assert page.status_code == 400
    assert "The file is missing the columns: origin_port, destination_port, departure_time, arrival_time." in page.text


def test_a_binary_file_gets_a_plain_message(data):
    page = client_for(data).post("/submit", files={"csv_file": ("x.png", b"\x89PNG\r\n\x1a\n\xff\xfe", "image/png")})
    assert "This file is not a readable CSV (UTF-8 text)." in page.text
    assert "codec" not in page.text


def test_a_file_over_1_mb_is_rejected(data):
    big = CSV + b"x" * MAX_UPLOAD_BYTES
    page = client_for(data).post("/submit", files={"csv_file": ("big.csv", big, "text/csv")})
    assert page.status_code == 413
    assert "larger than 1 MB" in page.text


# submit in demo mode: results stream one row per shipment

def demo_client(data):
    return client_for(data, FakeAI(), FakeLogic(), demo=True)


def test_demo_mode_shows_the_banner_on_every_page(data):
    client = demo_client(data)
    assert "Demo mode: fake AI and rules" in client.get("/").text
    assert "Demo mode: fake AI and rules" in client.post("/submit", data=good_rows(1)).text


def test_demo_mode_streams_one_row_per_shipment_in_order(data):
    page = demo_client(data).post("/submit", data=good_rows(3))
    assert page.status_code == 200
    assert page.headers["x-accel-buffering"] == "no"
    assert page.headers["content-type"].startswith("text/html")
    text = page.text
    positions = [text.index(f">{n} of 3<") for n in (1, 2, 3)]
    assert positions == sorted(positions)
    assert [text.index(f"SHP-00{n}") for n in (1, 2, 3)] == sorted(text.index(f"SHP-00{n}") for n in (1, 2, 3))
    assert text.index("<thead>") < positions[0]
    assert "Done: 3 of 3 shipments assessed." in text
    assert text.rstrip().endswith("</html>")
    assert len(data.find(SearchCriteria())) == 3


def test_result_rows_show_the_route_arrow_and_readable_primary_risk(data):
    text = demo_client(data).post("/submit", data=good_rows(1)).text
    assert '<td class="route" data-label="Route">SGSIN → NLRTM</td>' in text
    assert '<td data-label="Primary risk">Weather (Medium)</td>' in text
    assert "<dt>AI data fetched</dt>" in text


def test_result_rows_show_risk_and_outcome_as_text(data):
    text = demo_client(data).post("/submit", data=good_rows(3)).text
    assert '<span class="badge risk-high">High</span>' in text            # SHP-002 in the fakes
    assert '<span class="badge outcome-escalate">ESCALATE</span>' in text
    assert "AI unavailable" not in text
    assert "Not saved" not in text


def test_ids_continue_after_earlier_submissions(data):
    client = demo_client(data)
    client.post("/submit", data=good_rows(2))
    assert "SHP-003" in client.post("/submit", data=good_rows(1)).text


class SaveFails(JsonDataManager):
    """Reads work, every save fails: the database went away after the IDs were given out."""

    def save(self, record):
        raise StorageError("Database is down")


def test_a_row_whose_save_failed_says_not_saved(tmp_path):
    data = SaveFails(tmp_path / "records.json", PORTS)
    text = demo_client(data).post("/submit", data=good_rows(2)).text
    assert text.count('<span class="badge badge-error">Not saved</span>') == 2
    assert "Database is down" in text
    assert "Done: 2 of 2 shipments assessed." in text


class BrokenAI:
    def assess(self, shipment):
        raise RuntimeError("boom")


def test_an_unexpected_error_ends_the_page_with_a_message(data):
    text = client_for(data, BrokenAI(), FakeLogic()).post("/submit", data=good_rows(2)).text
    assert "Assessment stopped after 0 of 2 shipments" in text
    assert "boom" not in text
    assert text.rstrip().endswith("</html>")


def test_invalid_rows_are_not_assessed_in_demo_mode(data):
    rows = good_rows(2)
    rows["destination_port"][0] = "SGSIN"
    page = demo_client(data).post("/submit", data=rows)
    assert page.status_code == 422
    assert "Row 1: Origin and destination are the same port" in page.text
    assert data.find(SearchCriteria()) == []


def test_streamed_rows_have_expandable_details(data):
    text = demo_client(data).post("/submit", data=good_rows(1)).text
    assert "<summary>Details for SHP-001</summary>" in text
    assert "Fake medium weather" in text
    assert "Fake rule: weather risk is Medium" in text


# search

def test_search_page_has_every_filter_with_a_label_and_the_dropdowns(data):
    text = client_for(data).get("/search").text
    for name in ("shipment_id", "origin", "destination", "departure_from", "departure_to",
                 "overall_risk", "outcome", "needs_human"):
        assert f'name="{name}"' in text
    assert '<option value="Extreme">Extreme</option>' in text
    assert '<option value="REJECT">REJECT</option>' in text
    assert text.count("<label>") == 8


def test_search_with_nothing_saved_offers_the_submit_page(data):
    text = client_for(data).get("/search").text
    assert "No records match." in text
    assert '<a href="/">Assess new shipments</a>' in text


def test_search_filters_and_shows_details(data):
    data.save(saved_record("SHP-001", risk="LOW"))
    data.save(saved_record("SHP-002", risk="HIGH", outcome="ESCALATE", needs_human=True))
    text = client_for(data).get("/search", params={"overall_risk": "High", "needs_human": "yes"}).text
    assert "1 record, newest first." in text
    assert '<th scope="row">SHP-002' in text and '<th scope="row">SHP-001' not in text
    assert "<summary>Details for SHP-002</summary>" in text
    assert "Heavy rain" in text                                   # a risk factor detail
    assert '<option value="High" selected>' in text              # the filter stays chosen


def test_search_without_filters_lists_everything(data):
    data.save(saved_record("SHP-001"))
    data.save(saved_record("SHP-002", fallback=True))
    text = client_for(data).get("/search").text
    assert "2 records, newest first." in text
    assert text.count('<span class="badge badge-warn">AI unavailable</span>') == 2   # row and details


def test_search_with_a_bad_filter_shows_the_error(data):
    text = client_for(data).get("/search", params={"departure_from": "2026-12-01", "origin": "<b>x</b>"}).text
    assert "is not a valid date" in text
    assert "&lt;b&gt;x&lt;/b&gt;" in text and "<b>x</b>" not in text


def test_search_with_a_risk_that_is_not_offered_is_an_error(data):
    text = client_for(data).get("/search", params={"overall_risk": "Severe"}).text
    assert "Overall risk: &#39;Severe&#39; is not one of Low, Medium, High, Extreme" in text


def test_search_finds_what_demo_mode_saved(data):
    client = demo_client(data)
    client.post("/submit", data=good_rows(3))
    text = client.get("/search", params={"outcome": "ESCALATE"}).text
    assert '<th scope="row">SHP-002' in text and '<th scope="row">SHP-001' not in text


# database unavailable

def test_notices_show_as_a_red_banner_on_every_page():
    data = UnavailableDataManager("Database unavailable: timed out")
    client = client_for(data, FakeAI(), FakeLogic(), demo=True, notices=[data.message])
    banner = '<div class="banner banner-error" role="alert">Database unavailable: timed out</div>'
    assert banner in client.get("/").text
    assert banner in client.get("/search").text
    assert banner in client.post("/submit", data=good_rows(1)).text


def test_submit_runs_nothing_when_saved_records_cannot_be_read():
    data = UnavailableDataManager("Database unavailable")
    page = client_for(data, FakeAI(), FakeLogic(), demo=True).post("/submit", data=good_rows(2))
    assert page.status_code == 503
    assert "Cannot assign shipment IDs: saved records could not be read. Nothing was assessed." in page.text
    assert "1 of 2" not in page.text


def test_search_without_a_database_shows_the_message():
    data = UnavailableDataManager("Database unavailable: timed out")
    text = client_for(data).get("/search").text
    assert '<p class="alert alert-error" role="alert">Database unavailable: timed out</p>' in text


# main.create_app

@pytest.fixture
def env(monkeypatch, tmp_path):
    """A clean environment: a developer's own .env and shell settings must not change the tests."""
    monkeypatch.setattr(main, "load_dotenv", lambda *args, **kwargs: False)
    for name in ("DEMO_MODE", "DATA_BACKEND", "DATA_FILE", "DEMO_DATA_FILE", "MONGO_URI", "DB_NAME",
                 "GEMINI_API_KEY", "GEMINI_MODEL", "AI_CACHE_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_BACKEND", "json")
    monkeypatch.setenv("DATA_FILE", str(tmp_path / "records.json"))
    monkeypatch.setenv("DEMO_DATA_FILE", str(tmp_path / "demo.json"))
    return monkeypatch


def test_create_app_serves_the_input_page_with_the_real_ports(env):
    page = TestClient(main.create_app()).get("/")
    assert page.status_code == 200
    assert "SGSIN - Singapore" in page.text


def test_ai_is_not_connected_without_a_key(env):
    assert main.build_ai() is None


def test_ai_is_built_from_the_key_and_model(env, tmp_path):
    env.setenv("GEMINI_API_KEY", "test-key")
    env.setenv("GEMINI_MODEL", "test-model")
    env.setenv("AI_CACHE_FILE", str(tmp_path / "cache.json"))
    from ai_layer.ai_manager import AIManager
    assert isinstance(main.build_ai(), AIManager)


class RecordingSession:
    """Stands in for requests.Session: Gemini posts get a valid reply, feed requests fail. Remembers the URLs."""

    def __init__(self):
        self.posted = []

    def post(self, url, **kwargs):
        self.posted.append(url)
        return gemini_reply(valid_raw())

    def get(self, url, **kwargs):
        raise requests.ConnectionError("no network in tests")


def test_build_ai_uses_gemini_model_and_ai_cache_file(env, tmp_path):
    cache = tmp_path / "chosen" / "cache.json"
    cache.parent.mkdir()
    env.setenv("GEMINI_API_KEY", "test-key")
    env.setenv("GEMINI_MODEL", "my-test-model")
    env.setenv("AI_CACHE_FILE", str(cache))
    session = RecordingSession()
    with patch("requests.Session", return_value=session):
        ai = main.build_ai()
    assessment = ai.assess(make_shipment())
    assert assessment.status.value == "LIVE"
    assert len(session.posted) == 1 and "/models/my-test-model:generateContent" in session.posted[0]
    assert cache.exists() and len(json.loads(cache.read_text(encoding="utf-8"))) == 1


def test_logic_is_built_with_the_data_manager_and_ports(data):
    from logic_layer.logic_manager import LogicManager
    logic = main.build_logic(data, PORTS)
    assert isinstance(logic, LogicManager)
    assert len(logic.rules) == 7


def test_build_data_uses_json_by_default(env):
    env.delenv("DATA_BACKEND")
    assert isinstance(main.build_data(PORTS), JsonDataManager)


def test_empty_settings_from_env_example_mean_the_defaults(env):
    env.setenv("DATA_BACKEND", "")
    env.setenv("DEMO_MODE", "")
    assert isinstance(main.build_data(PORTS), JsonDataManager)
    assert "Demo mode" not in TestClient(main.create_app()).get("/").text


def test_build_data_rejects_an_unknown_backend(env):
    env.setenv("DATA_BACKEND", "excel")
    with pytest.raises(ValueError):
        main.build_data(PORTS)


def test_create_app_in_demo_mode_assesses_with_the_fakes(env):
    env.setenv("DEMO_MODE", "1")
    client = TestClient(main.create_app())
    page = client.post("/submit", files={"csv_file": ("s.csv", CSV, "text/csv")})
    assert "Demo mode: fake AI and rules" in page.text
    assert "1 of 1" in page.text and "SHP-001" in page.text


def test_create_app_without_a_key_says_only_the_ai_is_not_connected(env):
    page = TestClient(main.create_app()).post("/submit", files={"csv_file": ("s.csv", CSV, "text/csv")})
    assert f"1 shipment is valid. {NO_AI}" in page.text
    assert "Demo mode" not in page.text


SHORT = "Database unavailable. Results will not be saved."


def test_build_data_without_mongo_settings_is_unavailable(env, caplog):
    env.setenv("DATA_BACKEND", "mongo")
    data = main.build_data(PORTS)
    assert isinstance(data, UnavailableDataManager)
    assert data.message == SHORT
    assert "MONGO_URI and DB_NAME must both be set" in caplog.text


def test_build_data_falls_back_when_mongo_cannot_be_reached(env):
    def unreachable(*args, **kwargs):
        raise StorageError("Cannot reach the database: timed out")
    env.setenv("DATA_BACKEND", "mongo")
    env.setenv("MONGO_URI", "mongodb://db.invalid")
    env.setenv("DB_NAME", "team4")
    env.setattr(main.MongoDataManager, "connect", unreachable)
    data = main.build_data(PORTS)
    assert isinstance(data, UnavailableDataManager)
    assert data.message == SHORT


def test_create_app_shows_the_banner_when_the_database_is_unavailable(env):
    env.setenv("DATA_BACKEND", "mongo")
    page = TestClient(main.create_app()).get("/")
    assert page.status_code == 200
    assert "banner-error" in page.text and "Database unavailable" in page.text


def test_demo_mode_keeps_its_records_apart_from_the_real_ones(env, tmp_path):
    env.setenv("DEMO_MODE", "1")
    env.setenv("DATA_BACKEND", "mongo")                      # ignored in demo mode
    page = TestClient(main.create_app()).post("/submit", files={"csv_file": ("s.csv", CSV, "text/csv")})
    assert "1 of 1" in page.text and "banner-error" not in page.text
    assert (tmp_path / "demo.json").exists()
    assert not (tmp_path / "records.json").exists()


@pytest.mark.parametrize("uri, db_name, driver_text", [
    ("mongodb://localhost:27017", "team 4", "cannot contain"),           # invalid database name
    ("mongodb://localhost:99999", "team4", "Port must be an integer"),   # invalid port
])
def test_bad_database_settings_show_only_the_short_message(env, caplog, uri, db_name, driver_text):
    env.setenv("DATA_BACKEND", "mongo")
    env.setenv("MONGO_URI", uri)
    env.setenv("DB_NAME", db_name)
    client = TestClient(main.create_app())
    home, search = client.get("/").text, client.get("/search").text
    assert f'<div class="banner banner-error" role="alert">{SHORT}</div>' in home
    assert f'<p class="alert alert-error" role="alert">{SHORT}</p>' in search
    assert driver_text not in home + search
    assert driver_text in caplog.text


def test_a_failed_mongo_save_shows_the_short_message_on_the_row(caplog):
    mongomock = pytest.importorskip("mongomock")
    from pymongo.errors import AutoReconnect
    from data_layer.mongo_data_manager import MongoDataManager
    collection = mongomock.MongoClient().db.records
    data = MongoDataManager(collection, PORTS)

    def lost(document):
        raise AutoReconnect("connection reset by peer")
    collection.insert_one = lost
    text = demo_client(data).post("/submit", data=good_rows(1)).text
    assert '<span class="badge badge-error">Not saved</span>' in text
    assert SHORT in text
    assert "connection reset" not in text
    assert "connection reset by peer" in caplog.text


def test_the_web_layer_does_not_import_main():
    import ast
    from pathlib import Path
    for path in (Path(__file__).resolve().parent.parent / "web").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        names += [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        assert "main" not in names, path


def test_the_runner_passed_in_is_the_one_used(data):
    calls = []

    def runner(shipments, ai, logic, data_manager):
        calls.append([s.shipment_id for s in shipments])
        return iter(())
    client = TestClient(create_web_app(make_io(data), FakeAI(), FakeLogic(), data, run=runner))
    assert "Done: 0 of 2" in client.post("/submit", data=good_rows(2)).text
    assert calls == [["SHP-001", "SHP-002"]]


def test_create_app_reads_env_through_the_name_the_fixture_replaces(env):
    calls = []
    env.setattr(main, "load_dotenv", lambda *args, **kwargs: calls.append(args))
    main.create_app()
    assert calls == [()]


class SlowFirstAI(FakeAI):
    """FakeAI whose first two calls wait for each other, so two submissions overlap before either saves."""

    def __init__(self):
        self.__barrier = threading.Barrier(2, timeout=10)
        self.__calls = 0
        self.__lock = threading.Lock()

    def assess(self, shipment):
        with self.__lock:
            self.__calls += 1
            wait = self.__calls <= 2
        if wait:
            self.__barrier.wait()
        return super().assess(shipment)


def test_overlapping_submissions_get_distinct_ids_and_every_row_saves(data):
    app = create_web_app(make_io(data), SlowFirstAI(), FakeLogic(), data, run=main.assess_shipments)
    pages = []

    def submit():
        pages.append(TestClient(app).post("/submit", data=good_rows(3)).text)

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert len(pages) == 2
    assert all("Not saved" not in page for page in pages)
    saved = sorted(r.shipment.shipment_id for r in data.find(SearchCriteria()))
    assert saved == [f"SHP-{n:03d}" for n in range(1, 7)]


def test_create_app_sets_up_logging_only_when_nothing_has(env):
    root = logging.getLogger()
    with patch.object(root, "handlers", []), patch("main.logging.basicConfig") as basic:
        main.create_app()
    basic.assert_called_once()
    assert basic.call_args.kwargs["level"] == logging.INFO
    with patch.object(root, "handlers", [logging.NullHandler()]), patch("main.logging.basicConfig") as basic:
        main.create_app()
    basic.assert_not_called()
