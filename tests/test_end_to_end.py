"""The whole app through main.create_app: real IO, AI, Logic and JSON storage; only Gemini and the feeds are mocked.

No network: the Gemini client is Mock(spec=GeminiClient) and the context providers are stubs.
"""
from unittest.mock import Mock, patch
import pytest
from fastapi.testclient import TestClient
from ai_layer.ai_manager import AIManager
from ai_layer.ai_service_error import AIServiceError
from ai_layer.ai_settings import ALLOWED_LISTS
from ai_layer.context_provider import ContextProvider
from ai_layer.gemini_client import GeminiClient
import main


def reply(factors=(), primary="none", location="Route", impact="None", insights=()):
    """A Gemini reply that fits the response schema. By default nothing is wrong on the route."""
    return {"risk_factors": list(factors), "primary_risk_factor": primary, "affected_location": location,
            "expected_impact": impact, "confidence_score": 0.9, "conflicting_sources": False,
            "insights": list(insights)}


def risk(risk_type, severity, location="SGSIN", source="open_meteo_weather"):
    return {"type": risk_type, "severity": severity, "location": location, "source": source, "detail": "test"}


CALM = reply()
STORMY = reply([risk("weather", "Medium")], primary="weather", location="SGSIN", impact="Delay")
PIRACY = reply([risk("piracy_threat", "Medium", "Route", "gdelt_news")], primary="piracy_threat",
               impact="Cost Increase")


def rows(*dates):
    """Typed SGSIN -> NLRTM rows, one per (departure, arrival) pair."""
    return {"origin_port": ["SGSIN"] * len(dates), "destination_port": ["NLRTM"] * len(dates),
            "departure_time": [d for d, _ in dates], "arrival_time": [a for _, a in dates]}


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("time.sleep"):
        yield


@pytest.fixture
def gemini():
    client = Mock(spec=GeminiClient)
    client.fingerprint.return_value = "end-to-end"
    client.complete.return_value = CALM
    return client


@pytest.fixture
def app(monkeypatch, tmp_path, gemini):
    """main.create_app with a clean environment, a temp JSON file and a real AIManager around the mock."""
    monkeypatch.setattr(main, "load_dotenv", lambda *args, **kwargs: False)
    for name in ("DEMO_MODE", "DATA_BACKEND", "DATA_FILE", "DEMO_DATA_FILE", "MONGO_URI", "DB_NAME",
                 "GEMINI_API_KEY", "GEMINI_MODEL", "AI_CACHE_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATA_FILE", str(tmp_path / "records.json"))
    providers = []
    for name in ("weather", "news"):
        provider = Mock(spec=ContextProvider)
        provider.name = name
        provider.fetch.return_value = None
        providers.append(provider)
    ai = AIManager(gemini, providers, tmp_path / "ai_cache.json", ALLOWED_LISTS)
    monkeypatch.setattr(main, "build_ai", lambda: ai)
    return TestClient(main.create_app())


def outcome(name):
    """The outcome cell of a summary row (the details row shows the badge again)."""
    return f'<td data-label="Outcome"><span class="badge outcome-{name.lower()}">{name}</span></td>'


def row_for(shipment_id):
    """The start of a summary row in the results or search table."""
    return f'<th scope="row">{shipment_id}'


def test_a_calm_route_proceeds(app):
    page = app.post("/submit", data=rows(("01/12/2026", "20/12/2026")))
    assert page.status_code == 200
    assert "1 of 1" in page.text and row_for("SHP-001") in page.text
    assert outcome("PROCEED") in page.text
    assert "AI unavailable" not in page.text
    assert "not connected" not in page.text


def test_piracy_is_insured(app, gemini):
    gemini.complete.return_value = PIRACY
    page = app.post("/submit", data=rows(("01/12/2026", "20/12/2026")))
    assert outcome("INSURE") in page.text
    assert "Premium Increase Required" in page.text


def test_a_failing_ai_is_marked_unavailable_and_escalated(app, gemini):
    gemini.complete.side_effect = AIServiceError("service down", retryable=False)
    page = app.post("/submit", data=rows(("01/12/2026", "20/12/2026"), ("02/12/2026", "21/12/2026")))
    assert "2 of 2" in page.text
    for shipment_id in ("SHP-001", "SHP-002"):
        assert f'{row_for(shipment_id)} <span class="badge badge-warn">AI unavailable</span>' in page.text
    assert page.text.count(outcome("ESCALATE")) == 2
    assert "Traceback" not in page.text


def test_a_recent_medium_shipment_puts_a_later_low_one_under_cautionary_override(app, gemini):
    gemini.complete.return_value = STORMY
    first = app.post("/submit", data=rows(("01/12/2026", "20/12/2026")))
    assert outcome("PROCEED") in first.text and "Proceed with monitoring" in first.text

    gemini.complete.return_value = CALM                 # other dates, so the cached reply is not used
    second = app.post("/submit", data=rows(("05/12/2026", "24/12/2026")))
    assert row_for("SHP-002") in second.text
    assert "Cautionary Override" in second.text
    assert outcome("ESCALATE") in second.text
    assert "Require human dispatcher sign-off" in second.text


def test_search_finds_the_saved_records(app, gemini):
    app.post("/submit", data=rows(("01/12/2026", "20/12/2026")))
    gemini.complete.return_value = PIRACY
    app.post("/submit", data=rows(("03/12/2026", "22/12/2026")))

    everything = app.get("/search")
    assert row_for("SHP-001") in everything.text and row_for("SHP-002") in everything.text

    insured = app.get("/search", params={"outcome": "INSURE"})
    assert row_for("SHP-002") in insured.text and row_for("SHP-001") not in insured.text
