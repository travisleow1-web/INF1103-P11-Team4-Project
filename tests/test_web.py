"""Web pages through FastAPI's TestClient, with a temp-file JSON data manager. No network."""
import pytest
from fastapi.testclient import TestClient
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
    return TestClient(create_web_app(make_io(data), ai, logic, data, demo, notices))


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

def test_valid_rows_without_ai_say_not_connected(data):
    page = client_for(data).post("/submit", data=good_rows(2))
    assert page.status_code == 200
    assert "2 shipments are valid. AI and Logic are not connected yet." in page.text


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
    assert "Row 2: origin: unknown port &#39;XXXXX&#39;; arrival: &#39;2026-12-20&#39; is not a valid date" in page.text
    assert 'value="XXXXX"' in page.text
    assert "not connected" not in page.text


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


def test_a_row_whose_save_failed_says_not_saved():
    data = UnavailableDataManager("Database is down")
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
    assert "Row 1: origin and destination are the same port" in page.text
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


def test_search_without_a_database_shows_the_message():
    data = UnavailableDataManager("Database unavailable: timed out")
    text = client_for(data).get("/search").text
    assert '<p class="alert alert-error" role="alert">Database unavailable: timed out</p>' in text


# main.create_app

@pytest.fixture
def env(monkeypatch, tmp_path):
    for name in ("DEMO_MODE", "MONGO_URI", "DB_NAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_BACKEND", "json")
    monkeypatch.setenv("DATA_FILE", str(tmp_path / "records.json"))
    return monkeypatch


def test_create_app_serves_the_input_page_with_the_real_ports(env):
    page = TestClient(main.create_app()).get("/")
    assert page.status_code == 200
    assert "SGSIN - Singapore" in page.text


def test_ai_and_logic_are_not_connected_in_the_baseline():
    assert main.build_ai() is None
    assert main.build_logic(None, PORTS) is None


def test_build_data_uses_json_by_default(env):
    env.delenv("DATA_BACKEND")
    assert isinstance(main.build_data(PORTS), JsonDataManager)


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


def test_create_app_without_demo_mode_says_not_connected(env):
    page = TestClient(main.create_app()).post("/submit", files={"csv_file": ("s.csv", CSV, "text/csv")})
    assert "AI and Logic are not connected yet." in page.text
    assert "Demo mode" not in page.text


def test_build_data_without_mongo_settings_is_unavailable(env):
    env.setenv("DATA_BACKEND", "mongo")
    data = main.build_data(PORTS)
    assert isinstance(data, UnavailableDataManager)
    assert "MONGO_URI and DB_NAME must both be set" in data.message


def test_build_data_falls_back_when_mongo_cannot_be_reached(env):
    def unreachable(*args, **kwargs):
        raise StorageError("Cannot reach the database: timed out")
    env.setenv("DATA_BACKEND", "mongo")
    env.setenv("MONGO_URI", "mongodb://db.invalid")
    env.setenv("DB_NAME", "team4")
    env.setattr(main.MongoDataManager, "connect", unreachable)
    data = main.build_data(PORTS)
    assert isinstance(data, UnavailableDataManager)
    assert "timed out" in data.message


def test_create_app_shows_the_banner_when_the_database_is_unavailable(env):
    env.setenv("DATA_BACKEND", "mongo")
    page = TestClient(main.create_app()).get("/")
    assert page.status_code == 200
    assert "banner-error" in page.text and "Database unavailable" in page.text
