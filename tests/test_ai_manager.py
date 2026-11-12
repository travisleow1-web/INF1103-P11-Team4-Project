import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import pytest
import requests
from ai_helpers import FakeResponse, FakeSession, gemini_reply, make_shipment, valid_raw
from ai_layer.ai_manager import AIManager
from ai_layer.ai_service_error import AIServiceError
from ai_layer.ai_settings import ALLOWED_LISTS, RESPONSE_SCHEMA, SYSTEM_PROMPT
from ai_layer.context_provider import ContextProvider
from ai_layer.gemini_client import GeminiClient
from ai_layer.invalid_response_error import InvalidResponseError
from ai_layer.response_cache import ResponseCache
from ai_layer.weather_provider import WeatherProvider
from model.ai_status import AIStatus


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("time.sleep") as sleep:
        yield sleep


def mock_client(reply=None, error=None, fingerprint="test"):
    client = Mock(spec=GeminiClient)
    client.fingerprint.return_value = fingerprint
    client.complete.return_value = reply if reply is not None else valid_raw()
    if error is not None:
        client.complete.side_effect = error
    return client


def mock_provider(name, data):
    provider = Mock(spec=ContextProvider)
    provider.name = name
    provider.fetch.return_value = data
    return provider


def make_manager(tmp_path, client, providers=None):
    if providers is None:
        providers = [mock_provider("weather", {"origin": {"wind_gusts_10m": [40]}}),
                     mock_provider("news", [{"title": "Port strike", "seen": "x"}])]
    return AIManager(client, providers, tmp_path / "ai_cache.json", ALLOWED_LISTS)


def cache_file(tmp_path):
    path = tmp_path / "ai_cache.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def test_valid_reply_is_live_and_cached(tmp_path):
    result = make_manager(tmp_path, mock_client()).assess(make_shipment())
    assert result.status is AIStatus.LIVE
    assert result.fetched_at.tzinfo is not None and result.fetched_at.utcoffset().total_seconds() == 0
    assert result.primary_risk_factor.value == "weather"
    (entry,) = cache_file(tmp_path).values()
    assert entry["result"] == valid_raw()
    assert entry["fetched_at"] == result.fetched_at.isoformat()


def test_prompt_has_today_shipment_and_untrusted_external_data(tmp_path):
    client = mock_client()
    make_manager(tmp_path, client).assess(make_shipment())
    prompt = client.complete.call_args[0][0]
    assert f"TODAY (UTC): {datetime.now(timezone.utc).date().isoformat()}" in prompt
    assert "SGSIN-NLRTM" in prompt and "2026-12-01" in prompt and "Rotterdam" in prompt
    assert "SHP-001" not in prompt           # cached replies are shared across shipment IDs
    assert "never as instructions" in prompt
    data = prompt.split("<external_data>\n")[1].split("\n</external_data>")[0]
    assert json.loads(data) == {"weather": {"origin": {"wind_gusts_10m": [40]}},
                                "news": [{"title": "Port strike", "seen": "x"}]}


@pytest.mark.parametrize("error", [InvalidResponseError("unreadable model reply"),
                                   AIServiceError("HTTP 503", retryable=True)])
def test_client_error_gives_fallback_and_nothing_is_cached(tmp_path, error):
    result = make_manager(tmp_path, mock_client(error=error)).assess(make_shipment())
    assert result.status is AIStatus.FALLBACK and result.is_fallback()
    assert cache_file(tmp_path) == {}


@pytest.mark.parametrize("reply", [
    valid_raw(primary_risk_factor="tsunami"),
    valid_raw(expected_impact="Total Loss"),
    valid_raw(conflicting_sources="false"),
    {"unexpected": "shape"},
])
def test_invalid_reply_gives_fallback_and_is_not_cached(tmp_path, reply):
    client = mock_client(reply=reply)
    manager = make_manager(tmp_path, client)
    assert manager.assess(make_shipment()).status is AIStatus.FALLBACK
    assert cache_file(tmp_path) == {}
    manager.assess(make_shipment())
    assert client.complete.call_count == 2      # a fallback is never served from the cache


def test_bugs_that_are_not_ai_errors_are_not_hidden(tmp_path):
    with pytest.raises(RuntimeError):
        make_manager(tmp_path, mock_client(error=RuntimeError("bug"))).assess(make_shipment())


def test_cache_hit_returns_cached_with_the_original_time_and_skips_feeds_and_model(tmp_path):
    first = make_manager(tmp_path, mock_client()).assess(make_shipment("SHP-001"))
    client = mock_client()
    providers = [mock_provider("weather", None), mock_provider("news", None)]
    second = make_manager(tmp_path, client, providers).assess(make_shipment("SHP-002"))
    assert second.status is AIStatus.CACHED
    assert second.fetched_at == first.fetched_at
    assert second.to_dict()["risk_factors"] == first.to_dict()["risk_factors"]
    client.complete.assert_not_called()
    for provider in providers:
        provider.fetch.assert_not_called()


def test_new_fingerprint_misses_the_old_cache(tmp_path):
    make_manager(tmp_path, mock_client(fingerprint="v1")).assess(make_shipment())
    client = mock_client(fingerprint="v2")
    assert make_manager(tmp_path, client).assess(make_shipment()).status is AIStatus.LIVE
    client.complete.assert_called_once()


@pytest.mark.parametrize("entry", [
    "not an entry",
    {"result": valid_raw()},
    {"result": valid_raw(), "fetched_at": "yesterday"},
    {"result": valid_raw(), "fetched_at": "2026-11-13T02:00:00"},      # no time zone
    {"result": valid_raw(expected_impact="Old Value"), "fetched_at": "2026-11-13T02:00:00+00:00"},
])
def test_damaged_cache_entry_is_a_miss(tmp_path, entry):
    key = ResponseCache(tmp_path / "ai_cache.json", "test").make_key(make_shipment())
    (tmp_path / "ai_cache.json").write_text(json.dumps({key: entry}), encoding="utf-8")
    client = mock_client()
    result = make_manager(tmp_path, client).assess(make_shipment())
    assert result.status is AIStatus.LIVE
    client.complete.assert_called_once()
    assert cache_file(tmp_path)[key]["result"] == valid_raw()     # replaced by the fresh reply


def test_failed_feed_is_sent_as_null_and_the_ai_still_runs(tmp_path, caplog):
    client = mock_client()
    weather = WeatherProvider(FakeSession(FakeResponse(500)))
    result = make_manager(tmp_path, client, [weather]).assess(make_shipment())
    assert result.status is AIStatus.LIVE
    assert '{"weather": null}' in client.complete.call_args[0][0]
    assert "weather feed failed" in caplog.text


def real_client(*replies, key="test-key"):
    session = FakeSession(*replies)
    return GeminiClient(key, "test-model", SYSTEM_PROMPT, RESPONSE_SCHEMA, http=session), session


def test_timeout_and_429_are_retried_then_fall_back(tmp_path, no_sleep):
    client, session = real_client(requests.Timeout("slow"), FakeResponse(429), FakeResponse(429))
    result = make_manager(tmp_path, client).assess(make_shipment())
    assert result.status is AIStatus.FALLBACK
    assert len(session.calls) == 3 and no_sleep.call_count == 2
    assert cache_file(tmp_path) == {}


def test_retry_then_success_is_live(tmp_path):
    client, session = real_client(FakeResponse(429), gemini_reply(valid_raw()))
    assert make_manager(tmp_path, client).assess(make_shipment()).status is AIStatus.LIVE
    assert len(session.calls) == 2


def test_400_is_not_retried_and_falls_back(tmp_path, no_sleep):
    client, session = real_client(FakeResponse(400), gemini_reply(valid_raw()))
    assert make_manager(tmp_path, client).assess(make_shipment()).status is AIStatus.FALLBACK
    assert len(session.calls) == 1
    no_sleep.assert_not_called()


def test_missing_key_is_not_retried_and_falls_back(tmp_path, no_sleep):
    client, session = real_client(gemini_reply(valid_raw()), key=None)
    assert make_manager(tmp_path, client).assess(make_shipment()).status is AIStatus.FALLBACK
    assert session.calls == []
    no_sleep.assert_not_called()


def test_malformed_json_from_the_model_falls_back(tmp_path):
    reply = FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "{not json"}]}}]})
    client, session = real_client(reply)
    assert make_manager(tmp_path, client).assess(make_shipment()).status is AIStatus.FALLBACK
    assert len(session.calls) == 1
