"""Web pages through FastAPI's TestClient, with a temp-file JSON data manager. No network."""
import json
import logging
import re
import threading
from datetime import date
from unittest.mock import patch
import pytest
import requests
from fastapi.testclient import TestClient
from ai_helpers import gemini_reply, make_shipment, valid_raw
from helpers import PORTS, make_io, saved_record
from fakes import FakeAI, FakeLogic
from data_layer.json_data_manager import JsonDataManager
from data_layer.unavailable_data_manager import UnavailableDataManager
from model.fetch_event import FetchEvent
from model.fetch_stage import FetchStage
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


def test_input_page_dates_have_a_calendar_button_and_still_post_text(data):
    page = client_for(data).get("/").text
    assert page.count('class="date-field"') == 2
    assert page.count('data-range="start" data-gap="0"') == 1
    assert page.count('data-range="end" data-gap="1"') == 1             # arrival must be after departure
    assert page.count('class="date-button"') == 2 and page.count('type="date"') == 2
    assert page.count('name="departure_time"') == 1 and page.count('name="arrival_time"') == 1
    assert 'name="departure_time" placeholder="DD/MM/YYYY"' in page      # the text box is what is submitted
    assert '<script src="/static/date_picker.js?v=' in page


def test_the_invalid_mark_stays_on_the_text_box_not_the_hidden_picker(data):
    rows = good_rows(1)
    rows["arrival_time"][0] = "nonsense"
    page = client_for(data).post("/submit", data=rows).text
    assert page.count('aria-invalid="true"') == 4                        # four text boxes in the bad row
    assert 'type="date" class="date-native" tabindex="-1" aria-hidden="true">' in page


def test_search_page_date_filters_are_a_start_and_an_end_picker(data):
    page = client_for(data).get("/search").text
    assert page.count('class="date-field"') == 2
    assert page.count('data-range="start" data-gap="0"') == 1
    assert page.count('data-range="end" data-gap="0"') == 1              # same day is allowed
    assert '<script src="/static/date_picker.js?v=' in page


def test_pages_link_the_styles_and_scripts_with_a_version_so_browsers_reload_changes(data):
    client = client_for(data)
    for url in ("/", "/search"):
        page = client.get(url).text
        assert re.search(r'href="/static/style\.css\?v=\d+"', page)
        assert re.search(r'src="/static/date_picker\.js\?v=\d+"', page)
    link = re.search(r'/static/style\.css\?v=\d+', client.get("/").text).group(0)
    assert client.get(link).status_code == 200                           # the query string is ignored by the server


def test_static_files_are_served(data):
    client = client_for(data)
    assert client.get("/static/style.css").status_code == 200
    assert "add-row" in client.get("/static/add_row.js").text
    assert "showPicker" in client.get("/static/date_picker.js").text


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
    assert '<span class="badge badge-warn">AI unavailable</span>' not in text
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


class BrokenAI(FakeAI):
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
    assert len(logic.rules) == 8


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

    def runner(shipments, ai, logic, data_manager, replace=False):
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
        super().__init__()
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


def test_demo_mode_report_leads_the_results_and_the_dates_stay_hidden_until_switched_on(data):
    from datetime import date, timedelta
    leave = date.today() + timedelta(days=5)
    rows = good_rows(3)
    rows["departure_time"] = [leave.strftime("%d/%m/%Y")] * 3
    rows["arrival_time"] = [(leave + timedelta(days=9)).strftime("%d/%m/%Y")] * 3
    text = demo_client(data).post("/submit", data=rows).text           # SHP-002 is the fake AI's high risk
    assert '<main class="stream">' in text                              # CSS shows the report above the table
    assert text.index('<table class="results">') < text.index('class="report"')    # it is sent after the rows
    report = text[text.index('class="report"'):]
    assert "1 of 1 high-risk shipment has a new date" in report and "Show suggested dates" in report
    assert 'for="show-dates"' in report and text.count('id="show-dates"') == 1
    assert text.index('id="show-dates"') < text.index('<table class="results">')   # before the table, so CSS reaches the rows
    assert text.count('class="reschedule-row"') == 1                    # one hidden line, under SHP-002 only
    row = text[text.index('class="reschedule-row"'):]
    assert f"{leave + timedelta(days=4):%d/%m/%Y} to " in row and "4 days later" in row
    assert "meets High weather risk" in row
    assert "Suggested departure" not in text


def test_search_shows_the_summary_and_hidden_date_lines(data):
    client = demo_client(data)
    client.post("/submit", data=good_rows(3))
    page = client.get("/search").text
    assert "Summary of these records" in page and "Show suggested dates" in page
    assert page.count('class="reschedule-row"') == 1 and page.count('id="show-dates"') == 1


# re-running shipments the AI could not assess

def has_rerun_form(text, shipment_id):
    """True if the page has a Re-run form for that shipment."""
    return re.search(rf'action="/rerun"[^>]*>\s*<input type="hidden" name="shipment_id" value="{shipment_id}">', text) is not None


def failed_run(data, count=9):
    """Submit count shipments with the demo AI: the ninth fails the first time. Returns the client."""
    client = client_for(data, FakeAI(), FakeLogic(), demo=True)
    client.post("/submit", data=good_rows(count))
    return client


def test_a_failed_shipment_has_a_rerun_button_in_the_results_and_in_the_report(data):
    failed_run(data)
    text = client_for(data, FakeAI(), FakeLogic(), demo=True).get("/search").text
    assert has_rerun_form(text, "SHP-009") and "Re-run it" in text
    assert not has_rerun_form(text, "SHP-001")                      # only the failed one


def test_the_results_page_of_a_run_offers_the_rerun_for_the_failed_row(data):
    client = client_for(data, FakeAI(), FakeLogic(), demo=True)
    text = client.post("/submit", data=good_rows(9)).text
    assert has_rerun_form(text, "SHP-009") and "Re-run it" in text
    assert text.count('name="shipment_id" value="SHP-009"') == 2     # the row's button and the report's


def test_rerun_assesses_the_shipment_again_and_replaces_its_record(data):
    client = client_for(data, FakeAI(), FakeLogic(), demo=True)
    client.post("/submit", data=good_rows(9))
    text = client.post("/rerun", data={"shipment_id": ["SHP-009"]}).text
    assert "again, replacing the saved record." in text and "Done: 1 of 1" in text
    saved = data.find(SearchCriteria())
    assert len(saved) == 9 and saved[0].shipment.shipment_id == "SHP-009"
    assert not saved[0].assessment.is_fallback()
    assert not has_rerun_form(client.get("/search").text, "SHP-009")   # nothing left to re-run


def test_rerun_of_several_shipments_runs_each_once(data):
    client = client_for(data, FakeAI(), FakeLogic(), demo=True)
    client.post("/submit", data=good_rows(18))                      # SHP-009 and SHP-018 fail
    text = client.post("/rerun", data={"shipment_id": ["SHP-009", "SHP-018", "SHP-009"]}).text
    assert "Done: 2 of 2" in text
    assert len(data.find(SearchCriteria())) == 18


def test_rerun_skips_shipments_that_are_not_failed_and_says_so(data):
    client = client_for(data, FakeAI(), FakeLogic(), demo=True)
    client.post("/submit", data=good_rows(9))
    text = client.post("/rerun", data={"shipment_id": ["SHP-009", "SHP-001", "SHP-077"]}).text
    assert "Done: 1 of 1" in text
    assert "Not re-run (not saved, or already assessed by the AI): SHP-001, SHP-077." in text


def test_rerun_with_nothing_to_run_is_an_error_and_changes_nothing(data):
    client = client_for(data, FakeAI(), FakeLogic(), demo=True)
    client.post("/submit", data=good_rows(3))
    before = [(r.shipment.shipment_id, r.saved_at) for r in data.find(SearchCriteria())]
    page = client.post("/rerun", data={"shipment_id": ["SHP-001"]})
    assert page.status_code == 400 and "Nothing was re-run" in page.text
    assert [(r.shipment.shipment_id, r.saved_at) for r in data.find(SearchCriteria())] == before


def test_rerun_without_an_id_is_an_error(data):
    page = client_for(data, FakeAI(), FakeLogic(), demo=True).post("/rerun")
    assert page.status_code == 400 and "Choose at least one shipment to re-run." in page.text


def test_rerun_when_the_ai_is_not_connected_is_refused(data):
    page = client_for(data).post("/rerun", data={"shipment_id": ["SHP-001"]})
    assert page.status_code == 503 and "Nothing was re-run." in page.text


def test_rerun_when_the_saved_records_cannot_be_read_shows_the_storage_error():
    data = UnavailableDataManager("Database is down")
    page = client_for(data, FakeAI(), FakeLogic()).post("/rerun", data={"shipment_id": ["SHP-001"]})
    assert page.status_code == 503 and "Database is down Nothing was re-run." in page.text


def test_the_ids_in_a_rerun_form_are_escaped(data):
    data.save(saved_record("SHP-001", fallback=True))
    text = client_for(data, FakeAI(), FakeLogic()).post("/rerun", data={"shipment_id": ["SHP-001", "<b>x</b>"]}).text
    assert "<B>X</B>" not in text and "&lt;B&gt;X&lt;/B&gt;" in text      # IDs are shown upper-cased, and escaped


# sorting rows when the suggested dates are shown

def ranks_by_id(text):
    """{shipment id: data-rank} for each summary row on the page."""
    return {i: r for r, i in re.findall(r'<tr class="summary" data-rank="(\d)">\s*<th scope="row">(SHP-\d+)', text)}


def test_each_row_is_ranked_so_rows_with_a_new_date_can_come_first(data):
    client = client_for(data, FakeAI(), FakeLogic(), demo=True)
    client.post("/submit", data=good_rows(6))           # SHP-002 and SHP-005 are high risk with a new date
    found = ranks_by_id(client.get("/search").text)
    assert found == {"SHP-001": "2", "SHP-002": "0", "SHP-003": "2", "SHP-004": "2", "SHP-005": "0", "SHP-006": "2"}


def test_a_high_risk_row_with_no_new_date_is_ranked_between(data):
    data.save(saved_record("SHP-001", risk="HIGH", outcome="ESCALATE", needs_human=True))      # high, no date
    data.save(saved_record("SHP-002", risk="HIGH", outcome="ESCALATE", needs_human=True,
                           reschedule=(date(2026, 12, 5), date(2026, 12, 30), "Clear from 5 December")))
    data.save(saved_record("SHP-003"))
    page = client_for(data).get("/search").text
    assert ranks_by_id(page) == {"SHP-001": "1", "SHP-002": "0", "SHP-003": "2"}


def test_the_results_and_search_pages_load_the_sorting_script(data):
    client = client_for(data, FakeAI(), FakeLogic(), demo=True)
    run = client.post("/submit", data=good_rows(1)).text
    search = client.get("/search").text
    assert re.search(r'<script src="/static/show_dates\.js\?v=\d+"></script>', run)
    assert re.search(r'<script src="/static/show_dates\.js\?v=\d+"></script>', search)


# the date line: planned and suggested side by side, then why

def plan_cells(text):
    """(label, text) of each cell in the first date line on the page."""
    line = text[text.index('class="plan"'):text.index("</tr>", text.index('class="plan"'))]
    cells = re.findall(r'<span class="plan-label">(\w+)</span>(.*?)</div>', line, flags=re.S)
    return [(label, " ".join(re.sub(r"<[^>]+>", " ", body).split())) for label, body in cells]


def test_a_new_date_is_shown_as_planned_then_suggested_then_why(data):
    data.save(saved_record("SHP-002", risk="HIGH", outcome="ESCALATE", needs_human=True,
                           reschedule=(date(2026, 12, 5), date(2026, 12, 24), "Clear from 5 December")))
    cells = plan_cells(client_for(data).get("/search").text)
    assert [label for label, _ in cells] == ["Planned", "Suggested", "Why"]
    assert cells[0][1] == "01/12/2026 to 28/12/2026"
    assert cells[1][1] == "Reschedule 05/12/2026 to 24/12/2026 (4 days later)"
    assert cells[2][1] == "Clear from 5 December"


def test_a_high_risk_shipment_with_no_new_date_shows_none_and_the_reason(data):
    data.save(saved_record("SHP-001", risk="HIGH", outcome="ESCALATE", needs_human=True))
    cells = plan_cells(client_for(data).get("/search").text)
    assert cells[1] == ("Suggested", "None")
    assert cells[2][1].startswith("No new date suggested:")


# loading messages: what the AI is doing while shipments are assessed

class OneStepAI(FakeAI):
    """FakeAI that also tells its listeners one message with HTML in it, and counts its listeners."""

    def __init__(self, detail="<b>x</b>"):
        super().__init__()
        self.listeners = []
        self.__detail = detail

    def add_listener(self, listener):
        self.listeners.append(listener)
        super().add_listener(listener)

    def remove_listener(self, listener):
        self.listeners.remove(listener)
        super().remove_listener(listener)

    def assess(self, shipment):
        for listener in self.listeners:
            listener.on_event(FetchEvent(shipment.shipment_id, FetchStage.RETRYING, 1, 3, self.__detail))
        return super().assess(shipment)


def status_texts(page):
    """The text of each status update on the page, in order (the ones that are scripts)."""
    return [json.loads(text) for text in re.findall(r'getElementById\("status"\)\.textContent = (".*?");</script>', page)]


def test_the_results_page_shows_what_the_ai_is_doing_for_each_shipment(data):
    page = client_for(data, FakeAI(), FakeLogic()).post("/submit", data=good_rows(2)).text
    assert 'id="status"' in page and 'role="status"' in page
    assert status_texts(page) == ["Assessing SHP-001 (1 of 2) - AI: fetching in progress...",
                                  "Assessing SHP-001 (1 of 2) - AI: fetching complete",
                                  "Assessing SHP-002 (2 of 2) - AI: fetching in progress...",
                                  "Assessing SHP-002 (2 of 2) - AI: fetching complete",
                                  ""]                                    # cleared when everything is done


def test_a_status_line_comes_before_the_row_it_is_about(data):
    page = client_for(data, FakeAI(), FakeLogic()).post("/submit", data=good_rows(1)).text
    assert page.index("fetching in progress") < page.index('<th scope="row">SHP-001')
    assert page.index('<th scope="row">SHP-001') < page.index("Done: 1 of 1")


def test_a_failed_fetch_is_shown_with_its_reason(data):
    client = client_for(data, FakeAI(), FakeLogic())
    page = client.post("/submit", data=good_rows(9)).text               # the ninth shipment fails the first time
    assert "Assessing SHP-009 (9 of 9) - AI: fetching failed (the demo AI did not answer), using fallback assessment" in status_texts(page)


def test_a_rerun_shows_the_loading_messages_too(data):
    client = client_for(data, FakeAI(), FakeLogic())
    client.post("/submit", data=good_rows(9))
    page = client.post("/rerun", data={"shipment_id": ["SHP-009"]}).text
    assert status_texts(page) == ["Assessing SHP-009 (1 of 1) - AI: fetching in progress...",
                                  "Assessing SHP-009 (1 of 1) - AI: fetching complete", ""]


def test_status_text_from_the_ai_is_escaped_in_the_page(data):
    page = client_for(data, OneStepAI(), FakeLogic()).post("/submit", data=good_rows(1)).text
    assert "<b>x</b>" not in page                                     # never raw in the HTML
    assert "attempt 1/3 failed (\\u003cb\\u003ex\\u003c/b\\u003e), trying again..." in page
    assert "attempt 1/3 failed (<b>x</b>), trying again..." in " ".join(status_texts(page))   # plain text in the browser


def test_the_page_stops_listening_when_it_is_done(data):
    ai = OneStepAI()
    client_for(data, ai, FakeLogic()).post("/submit", data=good_rows(2))
    assert ai.listeners == []


def test_the_page_stops_listening_when_the_assessment_fails(data):
    class Failing(OneStepAI):
        def assess(self, shipment):
            raise RuntimeError("boom")
    ai = Failing()
    page = client_for(data, ai, FakeLogic()).post("/submit", data=good_rows(2)).text
    assert "Assessment stopped after 0 of 2 shipments" in page and ai.listeners == []


def test_a_page_only_shows_the_messages_of_its_own_shipments():
    from queue import Queue
    from web.status_feed import StatusFeed
    out = Queue()
    feed = StatusFeed(["SHP-001"], out)
    feed.on_event(FetchEvent("SHP-001", FetchStage.STARTED))
    feed.on_event(FetchEvent("SHP-777", FetchStage.STARTED))          # another visitor's shipment
    assert out.qsize() == 1 and out.get()[1].shipment_id == "SHP-001"


def test_demo_mode_shows_the_loading_messages_too(env):
    env.setenv("DEMO_MODE", "1")
    page = TestClient(main.create_app()).post("/submit", data=good_rows(1)).text
    assert "Assessing SHP-001 (1 of 1) - AI: fetching in progress..." in status_texts(page)
