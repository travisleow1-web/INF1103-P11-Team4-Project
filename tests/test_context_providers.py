import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
import requests
from ai_helpers import FakeResponse, FakeSession, make_shipment
from ai_layer.context_provider import ContextProvider
from ai_layer.news_provider import NewsProvider
from ai_layer.weather_provider import WeatherProvider


def hourly(**values):
    return FakeResponse(200, {"hourly": values})


def test_context_provider_is_abstract():
    with pytest.raises(TypeError):
        ContextProvider("x", FakeSession())


# ---- weather ----

def test_future_shipment_gets_the_forecast_for_both_ports():
    session = FakeSession(hourly(wind_gusts_10m=[50]), hourly(wave_height=[2.0]),
                          hourly(wind_gusts_10m=[30]), hourly(wave_height=[1.0]))
    provider = WeatherProvider(session)
    result = provider.fetch(make_shipment())
    assert provider.name == "weather"
    assert result == {"origin": {"wind_gusts_10m": [50], "wave_height": [2.0]},
                      "destination": {"wind_gusts_10m": [30], "wave_height": [1.0]}}
    urls = [url for _, url, _ in session.calls]
    assert urls[0] == "https://api.open-meteo.com/v1/forecast"
    assert "marine" in urls[1]
    first_params = session.calls[0][2]["params"]
    assert first_params["latitude"] == 1.26 and first_params["forecast_days"] == 16


def test_recently_departed_shipment_gets_historical_weather():
    today = datetime.now(timezone.utc).date()
    shipment = make_shipment(departure=today - timedelta(days=10), arrival=today + timedelta(days=5))
    replies = []
    for _ in range(2):
        replies += [hourly(wind_gusts_10m=[40]), hourly(wave_height=[1.5]), hourly(visibility=[None])]
    session = FakeSession(*replies)
    result = WeatherProvider(session).fetch(shipment)
    assert result["origin"]["historical_weather"] == {"visibility": [None]}
    params = session.calls[0][2]["params"]
    assert "historical-forecast" in session.calls[0][1]
    assert params["start_date"] == (today - timedelta(days=10)).isoformat()
    assert params["end_date"] == (today - timedelta(days=1)).isoformat()   # never today or later
    assert "archive" in session.calls[2][1]


def test_shipment_departed_too_long_ago_gets_the_forecast():
    today = datetime.now(timezone.utc).date()
    shipment = make_shipment(departure=today - timedelta(days=200), arrival=today - timedelta(days=150))
    session = FakeSession(*[hourly(a=[1])] * 4)
    WeatherProvider(session).fetch(shipment)
    assert "forecast_days" in session.calls[0][2]["params"]


@pytest.mark.parametrize("reply", [
    FakeResponse(500, {"error": True}),
    FakeResponse(200, bad_json=True),
    FakeResponse(200, {"no_hourly": 1}),
    requests.Timeout("slow"),
])
def test_failing_origin_gives_none_for_the_origin_only(reply, caplog):
    session = FakeSession(reply, hourly(wind_gusts_10m=[30]), hourly(wave_height=[1.0]))
    result = WeatherProvider(session).fetch(make_shipment())
    assert result == {"origin": None, "destination": {"wind_gusts_10m": [30], "wave_height": [1.0]}}
    assert "weather feed failed for SHP-001 at SGSIN" in caplog.text


def test_failing_destination_keeps_the_origin_data(caplog):
    session = FakeSession(hourly(wind_gusts_10m=[50]), hourly(wave_height=[2.0]),
                          hourly(wind_gusts_10m=[30]), FakeResponse(400, {"error": True}))
    result = WeatherProvider(session).fetch(make_shipment())
    assert result == {"origin": {"wind_gusts_10m": [50], "wave_height": [2.0]}, "destination": None}
    assert "at NLRTM" in caplog.text


class BrokenProvider(ContextProvider):
    """A feed whose request always fails."""

    def _request(self, shipment):
        raise RuntimeError("feed down")


def test_any_provider_failure_gives_none(caplog):
    provider = BrokenProvider("broken", FakeSession())
    assert provider.fetch(make_shipment()) is None
    assert "broken feed failed for SHP-001: feed down" in caplog.text


# ---- news ----

def gdelt(*titles):
    return FakeResponse(200, {"articles": [{"title": t, "seendate": "20261113T010000Z", "url": "x"}
                                           for t in titles]})


def test_news_returns_titles_and_dates():
    session = FakeSession(gdelt("Strike at Rotterdam port"))
    provider = NewsProvider(session)
    with patch("ai_layer.news_provider.time.sleep"):
        result = provider.fetch(make_shipment())
    assert provider.name == "news"
    assert result == [{"title": "Strike at Rotterdam port", "seen": "20261113T010000Z"}]
    query = session.calls[0][2]["params"]["query"]
    assert '"Singapore"' in query and '"Rotterdam"' in query


def test_news_without_articles_is_an_empty_list():
    with patch("ai_layer.news_provider.time.sleep"):
        assert NewsProvider(FakeSession(FakeResponse(200, {}))).fetch(make_shipment()) == []


@pytest.mark.parametrize("reply", [FakeResponse(429), FakeResponse(200, bad_json=True),
                                   requests.ConnectionError("down")])
def test_news_failure_gives_none(reply):
    with patch("ai_layer.news_provider.time.sleep"):
        assert NewsProvider(FakeSession(reply)).fetch(make_shipment()) is None


def test_first_call_does_not_wait_and_later_calls_wait_only_the_rest_of_the_gap():
    provider = NewsProvider(FakeSession(gdelt(), gdelt(), gdelt()), min_gap=5.0)
    with patch("ai_layer.news_provider.time.monotonic") as clock, \
            patch("ai_layer.news_provider.time.sleep") as sleep:
        clock.side_effect = [100.0, 102.0, 105.0, 120.0, 120.0]
        provider.fetch(make_shipment())        # first call: no wait
        sleep.assert_not_called()
        provider.fetch(make_shipment())        # 2 s after the first: waits 3 s
        sleep.assert_called_once_with(3.0)
        provider.fetch(make_shipment())        # 15 s later: no wait
        assert sleep.call_count == 1


def test_default_gap_leaves_headroom_over_gdelt_limit():
    provider = NewsProvider(FakeSession(gdelt(), gdelt()))
    with patch("ai_layer.news_provider.time.monotonic") as clock, \
            patch("ai_layer.news_provider.time.sleep") as sleep:
        clock.side_effect = [100.0, 101.0, 106.0]
        provider.fetch(make_shipment())
        provider.fetch(make_shipment())
        sleep.assert_called_once_with(5.0)          # 6 s gap from start to start


def test_failed_call_still_counts_for_the_gap():
    provider = NewsProvider(FakeSession(FakeResponse(503), gdelt()), min_gap=5.0)
    with patch("ai_layer.news_provider.time.monotonic") as clock, \
            patch("ai_layer.news_provider.time.sleep") as sleep:
        clock.side_effect = [100.0, 101.0, 101.0]
        assert provider.fetch(make_shipment()) is None
        provider.fetch(make_shipment())
        sleep.assert_called_once_with(4.0)


class TimedSession(FakeSession):
    """Records when each GET starts (real clock), thread-safe enough for list appends."""

    def __init__(self, count):
        super().__init__(*[gdelt() for _ in range(count)])
        self.starts = []

    def get(self, url, **kwargs):
        self.starts.append(time.monotonic())
        return super().get(url, **kwargs)


def test_concurrent_news_calls_keep_the_gap():
    session = TimedSession(4)
    provider = NewsProvider(session, min_gap=0.05)
    threads = [threading.Thread(target=provider.fetch, args=(make_shipment(),)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    starts = sorted(session.starts)
    assert len(starts) == 4
    assert all(later - earlier >= 0.045 for earlier, later in zip(starts, starts[1:]))
