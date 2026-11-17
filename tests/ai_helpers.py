import json
from datetime import date
from helpers import ROTTERDAM, SINGAPORE
from model.shipment import Shipment


class FakeResponse:
    def __init__(self, status_code=200, body=None, bad_json=False):
        self.status_code = status_code
        self.__body = body
        self.__bad_json = bad_json

    def json(self):
        if self.__bad_json:
            raise ValueError("not JSON")
        return self.__body


class FakeSession:
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
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(raw)}]}}]})


def valid_raw(**changes):
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


def make_shipment(shipment_id="SHP-001", departure=None, arrival=None):
    return Shipment(shipment_id, SINGAPORE, ROTTERDAM, departure or date(2026, 12, 1),
                    arrival or date(2026, 12, 20))
