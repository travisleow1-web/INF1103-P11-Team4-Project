import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from ai_layer.ai_manager import AIManager
from ai_layer.ai_settings import ALLOWED_LISTS, RESPONSE_SCHEMA, SYSTEM_PROMPT
from ai_layer.gemini_client import GeminiClient
from io_layer.console_status_display import ConsoleStatusDisplay
from model.ai_status import AIStatus
from model.fetch_event import FetchEvent
from model.fetch_listener import FetchListener
from model.fetch_stage import FetchStage
from model.port import Port
from model.shipment import Shipment

VALID_REPLY = {"risk_factors": [], "primary_risk_factor": "none", "affected_location": "Unknown",
               "expected_impact": "None", "confidence_score": 0.9, "conflicting_sources": False,
               "earliest_clear_departure": "", "insights": []}


class StubReply:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self.__body = body if body is not None else {}

    def json(self):
        return self.__body


def ok_reply(payload=VALID_REPLY):
    return StubReply(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]})


class StubSession:
    def __init__(self, *replies):
        self.__replies = list(replies)

    def post(self, *args, **kwargs):
        return self.__replies.pop(0)


class RecordingListener(FetchListener):
    def __init__(self):
        self.events = []

    def on_event(self, event: FetchEvent) -> None:
        self.events.append(event)

    def stages(self):
        return [e.stage for e in self.events]


class BrokenListener(FetchListener):
    def on_event(self, event: FetchEvent) -> None:
        raise RuntimeError("display crashed")


def make_shipment(shipment_id="SHP-001"):
    return Shipment(shipment_id, Port("SGSIN", "Singapore", "SG", 1.26, 103.8),
                    Port("NLRTM", "Rotterdam", "NL", 51.9, 4.5), date(2030, 1, 1), date(2030, 1, 20))


class FetchStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        sleeper = patch("ai_layer.gemini_client.time.sleep")     # retries must not really wait
        sleeper.start()
        self.addCleanup(sleeper.stop)
        self.listener = RecordingListener()

    def manager(self, *replies, listeners=None, max_retries=3):
        client = GeminiClient("test-key", "test-model", SYSTEM_PROMPT, RESPONSE_SCHEMA,
                              max_retries=max_retries, http=StubSession(*replies))
        return AIManager(client, [], Path(self.tmp.name) / "cache.json", ALLOWED_LISTS,
                         self.listener if listeners is None else listeners)

    def test_success_reports_started_then_succeeded(self):
        assessment = self.manager(ok_reply(), listeners=[self.listener]).assess(make_shipment())
        self.assertEqual(assessment.status, AIStatus.LIVE)
        self.assertEqual(self.listener.stages(), [FetchStage.STARTED, FetchStage.SUCCEEDED])
        self.assertTrue(all(e.shipment_id == "SHP-001" for e in self.listener.events))

    def test_retry_then_success_reports_retrying(self):
        manager = self.manager(StubReply(503), ok_reply(), listeners=[self.listener])
        assessment = manager.assess(make_shipment())
        self.assertEqual(assessment.status, AIStatus.LIVE)
        self.assertEqual(self.listener.stages(),
                         [FetchStage.STARTED, FetchStage.RETRYING, FetchStage.SUCCEEDED])
        retry = self.listener.events[1]
        self.assertEqual((retry.attempt, retry.max_attempts), (1, 3))
        self.assertIn("503", retry.detail)

    def test_all_attempts_failing_reports_failed_and_falls_back(self):
        manager = self.manager(StubReply(503), StubReply(503), StubReply(503), listeners=[self.listener])
        assessment = manager.assess(make_shipment())
        self.assertTrue(assessment.is_fallback())
        self.assertEqual(self.listener.stages(), [FetchStage.STARTED, FetchStage.RETRYING,
                                                  FetchStage.RETRYING, FetchStage.FAILED])
        self.assertIn("503", self.listener.events[-1].detail)

    def test_error_that_cannot_be_retried_fails_without_retrying(self):
        assessment = self.manager(StubReply(401), listeners=[self.listener]).assess(make_shipment())
        self.assertTrue(assessment.is_fallback())
        self.assertEqual(self.listener.stages(), [FetchStage.STARTED, FetchStage.FAILED])

    def test_malformed_model_reply_reports_failed(self):
        bad = ok_reply({"confidence_score": 5})          # breaks the agreed schema
        assessment = self.manager(bad, listeners=[self.listener]).assess(make_shipment())
        self.assertTrue(assessment.is_fallback())
        self.assertEqual(self.listener.stages(), [FetchStage.STARTED, FetchStage.FAILED])

    def test_cached_reply_reports_cache_hit_only(self):
        manager = self.manager(ok_reply(), listeners=[self.listener])
        manager.assess(make_shipment("SHP-001"))
        self.listener.events.clear()
        assessment = manager.assess(make_shipment("SHP-002"))      # same route and dates
        self.assertEqual(assessment.status, AIStatus.CACHED)
        self.assertEqual(self.listener.stages(), [FetchStage.CACHE_HIT])

    def test_broken_listener_does_not_stop_the_assessment(self):
        manager = self.manager(ok_reply(), listeners=[BrokenListener(), self.listener])
        assessment = manager.assess(make_shipment())
        self.assertEqual(assessment.status, AIStatus.LIVE)
        self.assertEqual(self.listener.stages(), [FetchStage.STARTED, FetchStage.SUCCEEDED])

    def test_works_with_no_listeners(self):
        assessment = self.manager(ok_reply(), listeners=[]).assess(make_shipment())
        self.assertEqual(assessment.status, AIStatus.LIVE)


class ConsoleStatusDisplayTests(unittest.TestCase):
    def show(self, event):
        out = io.StringIO()
        ConsoleStatusDisplay(out).on_event(event)
        return out.getvalue()

    def test_started_line(self):
        self.assertEqual(self.show(FetchEvent("SHP-001", FetchStage.STARTED)),
                         "[SHP-001] AI: fetching in progress...\n")

    def test_retrying_line_shows_attempt_and_reason(self):
        line = self.show(FetchEvent("SHP-002", FetchStage.RETRYING, 1, 3, "HTTP 503"))
        self.assertEqual(line, "[SHP-002] AI: attempt 1/3 failed (HTTP 503), trying again...\n")

    def test_failed_line_shows_reason(self):
        line = self.show(FetchEvent("SHP-003", FetchStage.FAILED, detail="network problem: Timeout"))
        self.assertIn("fetching failed (network problem: Timeout)", line)

    def test_every_stage_has_a_message(self):
        for stage in FetchStage:        # a new stage added without a message would raise KeyError
            self.assertIn("SHP-009", self.show(FetchEvent("SHP-009", stage, 1, 3, "why")))


if __name__ == "__main__":
    unittest.main()
