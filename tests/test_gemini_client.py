from unittest.mock import patch
import pytest
import requests
from ai_helpers import FakeResponse, FakeSession, gemini_reply
from ai_layer.ai_service_error import AIServiceError
from ai_layer.ai_settings import DEFAULT_MODEL, GEMINI_TIMEOUT, MAX_RETRIES, RESPONSE_SCHEMA, SYSTEM_PROMPT
from ai_layer.gemini_client import GeminiClient
from ai_layer.invalid_response_error import InvalidResponseError


def make_client(*replies, key="test-key", **kwargs):
    session = FakeSession(*replies)
    client = GeminiClient(key, DEFAULT_MODEL, SYSTEM_PROMPT, RESPONSE_SCHEMA, http=session, **kwargs)
    return client, session


@pytest.fixture(autouse=True)
def no_sleep():
    with patch("ai_layer.gemini_client.time.sleep") as sleep:
        yield sleep


def test_returns_the_reply_as_a_dict():
    client, session = make_client(gemini_reply({"confidence_score": 0.9}))
    assert client.complete("hello") == {"confidence_score": 0.9}
    method, url, kwargs = session.calls[0]
    assert DEFAULT_MODEL in url
    assert kwargs["headers"] == {"x-goog-api-key": "test-key"}
    assert kwargs["json"]["contents"][0]["parts"][0]["text"] == "hello"
    assert kwargs["json"]["systemInstruction"]["parts"][0]["text"] == SYSTEM_PROMPT
    assert kwargs["json"]["generationConfig"]["responseSchema"] == RESPONSE_SCHEMA
    assert kwargs["json"]["generationConfig"]["temperature"] == 0


def test_timeout_is_retried_then_succeeds(no_sleep):
    client, session = make_client(requests.Timeout("slow"), gemini_reply({"ok": True}))
    assert client.complete("p") == {"ok": True}
    assert len(session.calls) == 2
    assert no_sleep.call_count == 1


def test_429_is_retried_until_attempts_run_out(no_sleep):
    client, session = make_client(*[FakeResponse(429)] * 3)
    with pytest.raises(AIServiceError) as caught:
        client.complete("p")
    assert caught.value.retryable is True
    assert len(session.calls) == 3
    assert no_sleep.call_count == 2


def test_server_error_and_connection_error_are_retried():
    client, session = make_client(FakeResponse(503), requests.ConnectionError("down"),
                                  gemini_reply({"ok": True}))
    assert client.complete("p") == {"ok": True}
    assert len(session.calls) == 3


@pytest.mark.parametrize("status", [400, 401, 403])
def test_client_errors_are_not_retried(status, no_sleep):
    client, session = make_client(FakeResponse(status), gemini_reply({"ok": True}))
    with pytest.raises(AIServiceError) as caught:
        client.complete("p")
    assert caught.value.retryable is False
    assert len(session.calls) == 1
    no_sleep.assert_not_called()


@pytest.mark.parametrize("key", [None, ""])
def test_missing_key_is_not_retried_and_sends_nothing(key, no_sleep):
    client, session = make_client(gemini_reply({"ok": True}), key=key)
    with pytest.raises(AIServiceError) as caught:
        client.complete("p")
    assert caught.value.retryable is False
    assert session.calls == []
    no_sleep.assert_not_called()


@pytest.mark.parametrize("reply", [
    FakeResponse(200, bad_json=True),
    FakeResponse(200, {"candidates": []}),
    FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": "{not json"}]}}]}),
])
def test_unreadable_reply_is_invalid_and_not_retried(reply):
    client, session = make_client(reply, gemini_reply({"ok": True}))
    with pytest.raises(InvalidResponseError):
        client.complete("p")
    assert len(session.calls) == 1


def test_fingerprint_is_stable_and_changes_with_model_prompt_or_schema():
    base = GeminiClient("k", "m", "prompt", {"type": "OBJECT"}, http=FakeSession())
    same = GeminiClient("other-key", "m", "prompt", {"type": "OBJECT"}, http=FakeSession())
    assert base.fingerprint() == same.fingerprint()
    assert GeminiClient("k", "m", "prompt v2", {"type": "OBJECT"}).fingerprint() != base.fingerprint()
    assert GeminiClient("k", "m2", "prompt", {"type": "OBJECT"}).fingerprint() != base.fingerprint()
    assert GeminiClient("k", "m", "prompt", {"type": "ARRAY"}).fingerprint() != base.fingerprint()


def test_schema_is_copied():
    schema = {"type": "OBJECT"}
    client = GeminiClient("k", "m", "p", schema, http=FakeSession())
    before = client.fingerprint()
    schema["type"] = "ARRAY"
    assert client.fingerprint() == before


def test_key_is_stripped_before_use():
    client, session = make_client(gemini_reply({"ok": True}), key="  AIzaSECRET123\n")
    client.complete("p")
    assert session.calls[0][2]["headers"] == {"x-goog-api-key": "AIzaSECRET123"}


@pytest.mark.parametrize("key", ["   ", "\n", "AIza’SECRET", "AIza\nSECRET", "AIzaSECRETé"])
def test_malformed_key_counts_as_missing(key, no_sleep):
    client, session = make_client(gemini_reply({"ok": True}), key=key)
    with pytest.raises(AIServiceError) as caught:
        client.complete("p")
    assert str(caught.value) == "GEMINI_API_KEY is not set or invalid"
    assert caught.value.retryable is False
    assert session.calls == []


@pytest.mark.parametrize("error", [
    requests.exceptions.InvalidHeader("Invalid leading whitespace in header value b'AIzaSECRET123'"),
    UnicodeEncodeError("latin-1", "AIzaSECRET123", 0, 1, "ordinal not in range"),
    ValueError("bad value AIzaSECRET123"),
])
def test_request_errors_never_quote_their_text_and_are_not_retried(error):
    client, session = make_client(error, gemini_reply({"ok": True}), key="AIzaSECRET123")
    with pytest.raises(AIServiceError) as caught:
        client.complete("p")
    assert "AIzaSECRET123" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.retryable is False
    assert len(session.calls) == 1


def test_network_error_text_is_not_quoted(caplog):
    client, session = make_client(requests.ConnectionError("proxy said AIzaSECRET123"),
                                  gemini_reply({"ok": True}), key="AIzaSECRET123")
    assert client.complete("p") == {"ok": True}
    assert "AIzaSECRET123" not in caplog.text


def test_chunked_encoding_error_is_retried():
    client, session = make_client(requests.exceptions.ChunkedEncodingError("cut off"),
                                  gemini_reply({"ok": True}))
    assert client.complete("p") == {"ok": True}
    assert len(session.calls) == 2


def test_defaults_come_from_the_settings(no_sleep):
    client, session = make_client(*[FakeResponse(503)] * (MAX_RETRIES + 1))
    with pytest.raises(AIServiceError):
        client.complete("p")
    assert len(session.calls) == MAX_RETRIES
    assert session.calls[0][2]["timeout"] == GEMINI_TIMEOUT


@pytest.mark.parametrize("retries", [0, -1])
def test_max_retries_must_be_at_least_one(retries):
    with pytest.raises(ValueError):
        GeminiClient("k", "m", "p", {}, max_retries=retries, http=FakeSession())


def test_one_attempt_means_no_retry(no_sleep):
    client, session = make_client(FakeResponse(429), gemini_reply({"ok": True}), max_retries=1)
    with pytest.raises(AIServiceError):
        client.complete("p")
    assert len(session.calls) == 1
    no_sleep.assert_not_called()


def google_error(status_code, status, message):
    return FakeResponse(status_code, {"error": {"code": status_code, "status": status, "message": message}})


def test_an_error_reply_gives_googles_status_and_message():
    client, _ = make_client(google_error(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."))
    with pytest.raises(AIServiceError) as caught:
        client.complete("p")
    assert str(caught.value) == "HTTP 400 (INVALID_ARGUMENT: API key not valid. Please pass a valid API key.)"
    assert not caught.value.retryable


def test_a_retried_error_reply_keeps_the_reason():
    client, _ = make_client(*[google_error(503, "UNAVAILABLE", "The model is overloaded.")] * MAX_RETRIES)
    with pytest.raises(AIServiceError, match=r"HTTP 503 \(UNAVAILABLE: The model is overloaded.\)"):
        client.complete("p")


def test_a_long_reason_is_shortened_and_the_key_is_masked():
    client, _ = make_client(google_error(403, "PERMISSION_DENIED", "key test-key refused " + "x" * 500))
    with pytest.raises(AIServiceError) as caught:
        client.complete("p")
    text = str(caught.value)
    assert "test-key" not in text and "***" in text
    assert len(text) < 230 and text.endswith("...)")


@pytest.mark.parametrize("reply", [FakeResponse(400, None), FakeResponse(400, bad_json=True),
                                   FakeResponse(400, {"error": "plain text"}), FakeResponse(400, {"error": {}})])
def test_an_error_reply_without_a_usable_body_gives_only_the_status(reply):
    client, _ = make_client(reply)
    with pytest.raises(AIServiceError) as caught:
        client.complete("p")
    assert str(caught.value) == "HTTP 400"
