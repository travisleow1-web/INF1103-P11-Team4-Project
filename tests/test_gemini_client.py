from unittest.mock import patch
import pytest
import requests
from ai_helpers import FakeResponse, FakeSession, gemini_reply
from ai_layer.ai_service_error import AIServiceError
from ai_layer.ai_settings import DEFAULT_MODEL, RESPONSE_SCHEMA, SYSTEM_PROMPT
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
