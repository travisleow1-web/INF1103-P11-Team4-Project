"""Web pages through FastAPI's TestClient, with a temp-file JSON data manager. No network."""
import pytest
from fastapi.testclient import TestClient
from helpers import PORTS, make_io
from data_layer.json_data_manager import JsonDataManager
from web.app import MAX_UPLOAD_BYTES, create_web_app
import main

CSV = b"origin_port,destination_port,departure_time,arrival_time\nSGSIN,NLRTM,01/12/2026,20/12/2026\n"


def good_rows(count):
    return {"origin_port": ["SGSIN"] * count, "destination_port": ["NLRTM"] * count,
            "departure_time": ["01/12/2026"] * count, "arrival_time": ["20/12/2026"] * count}


@pytest.fixture
def data(tmp_path):
    return JsonDataManager(tmp_path / "records.json", PORTS)


def client_for(data, ai=None, logic=None, demo=False):
    return TestClient(create_web_app(make_io(data), ai, logic, data, demo))


# input page

def test_input_page_lists_the_ports_and_labels_every_box(data):
    page = client_for(data).get("/")
    assert page.status_code == 200
    assert '<option value="SGSIN - Singapore, SG">' in page.text
    assert page.text.count('placeholder="DD/MM/YYYY"') == 2
    assert page.text.count('<span class="sr-only">') == 4
    assert 'id="add-row"' in page.text
    assert "Demo mode" not in page.text


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
