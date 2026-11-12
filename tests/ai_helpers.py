"""Stand-ins for the AI layer tests. No network, no live Gemini."""
import json


class FakeResponse:
    """A requests.Response look-alike with a status code and a JSON body (or a JSON error)."""

    def __init__(self, status_code=200, body=None, bad_json=False):
        self.status_code = status_code
        self.__body = body
        self.__bad_json = bad_json

    def json(self):
        if self.__bad_json:
            raise ValueError("not JSON")
        return self.__body


class FakeSession:
    """Hands out queued replies (FakeResponse or an exception to raise) and records each call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __next(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def post(self, url, **kwargs):
        return self.__next("post", url, kwargs)

    def get(self, url, **kwargs):
        return self.__next("get", url, kwargs)


def gemini_reply(raw):
    """A Gemini HTTP reply whose text part holds `raw` as JSON text."""
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(raw)}]}}]})


def valid_raw(**changes):
    """A model reply that fits the schema: a high weather risk at Singapore and one delay insight."""
    raw = {
        "risk_factors": [
            {"type": "weather", "severity": "High", "location": "SGSIN",
             "source": "open_meteo_weather", "detail": "wind_gust_kmh=72"},
            {"type": "piracy_threat", "severity": "Low", "location": "Route",
             "source": "gdelt_news", "detail": "news_articles=1"},
        ],
        "primary_risk_factor": "weather",
        "affected_location": "SGSIN",
        "expected_impact": "Delay",
        "confidence_score": 0.8,
        "conflicting_sources": False,
        "insights": [
            {"code": "POTENTIAL_DELAY", "risk_type": "weather", "severity": "High",
             "location": "SGSIN", "estimated_delay_days": 2},
        ],
    }
    raw.update(changes)
    return raw
