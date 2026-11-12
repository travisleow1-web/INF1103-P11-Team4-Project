import copy
from datetime import datetime, timezone
import pytest
from ai_helpers import valid_raw
from ai_layer.ai_settings import ALLOWED_LISTS
from ai_layer.invalid_response_error import InvalidResponseError
from ai_layer.response_parser import ResponseParser
from model.ai_status import AIStatus
from model.risk_level import RiskLevel
from model.risk_type import RiskType

FETCHED_AT = datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc)
PARSER = ResponseParser(ALLOWED_LISTS)


def parse(raw, status=AIStatus.LIVE):
    return PARSER.parse(raw, status, FETCHED_AT)


def test_valid_reply_becomes_an_assessment():
    result = parse(valid_raw())
    assert result.status is AIStatus.LIVE
    assert result.fetched_at == FETCHED_AT
    assert result.primary_risk_factor is RiskType.WEATHER
    assert result.affected_location == "SGSIN"
    assert result.expected_impact == "Delay"
    assert result.confidence_score == 0.8
    assert result.conflicting_sources is False
    weather, piracy = result.risk_factors
    assert weather.type is RiskType.WEATHER and weather.severity is RiskLevel.HIGH
    assert weather.source == "open_meteo_weather" and weather.detail == "wind_gust_kmh=72"
    assert piracy.location == "Route"
    (insight,) = result.insights
    assert insight.code == "POTENTIAL_DELAY" and insight.estimated_delay_days == 2


def test_status_and_time_are_taken_from_the_caller():
    assert parse(valid_raw(), AIStatus.CACHED).status is AIStatus.CACHED


@pytest.mark.parametrize("text", ["HIGH", "high", "High", "Extreme"])
def test_severity_names_are_read_in_any_case(text):
    raw = valid_raw()
    raw["risk_factors"][0]["severity"] = text
    assert parse(raw).risk_factors[0].severity is RiskLevel.parse(text)


def test_unregistered_location_is_accepted():
    raw = valid_raw(affected_location="XXABC")
    assert parse(raw).affected_location == "XXABC"


def test_no_risks_reply():
    raw = valid_raw(risk_factors=[], insights=[], primary_risk_factor="none", expected_impact="None")
    result = parse(raw)
    assert result.risk_factors == () and result.primary_risk_factor is RiskType.NONE


def bad(path, value):
    """valid_raw() with one value replaced; path is a key or (list key, index, key)."""
    raw = copy.deepcopy(valid_raw())
    if isinstance(path, tuple):
        raw[path[0]][path[1]][path[2]] = value
    else:
        raw[path] = value
    return raw


@pytest.mark.parametrize("raw", [
    bad("primary_risk_factor", "tsunami"),
    bad("expected_impact", "Total Loss"),
    bad(("risk_factors", 0, "type"), "storm"),
    bad(("risk_factors", 0, "severity"), "Severe"),
    bad(("risk_factors", 0, "severity"), None),
    bad(("risk_factors", 0, "source"), "twitter"),
    bad(("insights", 0, "code"), "PANIC"),
    bad(("insights", 0, "risk_type"), "unknown"),
    bad(("insights", 0, "severity"), "medium-high"),
    bad(("insights", 0, "estimated_delay_days"), "soon"),
    bad(("insights", 0, "estimated_delay_days"), -1),
    bad("confidence_score", 1.5),
    bad("confidence_score", -0.1),
    bad("confidence_score", "0.8"),
    bad("confidence_score", True),
    bad("conflicting_sources", "false"),
    bad("conflicting_sources", 0),
    bad("risk_factors", "none"),
    bad("insights", None),
])
def test_any_invalid_value_rejects_the_whole_reply(raw):
    with pytest.raises(InvalidResponseError):
        parse(raw)


@pytest.mark.parametrize("key", list(valid_raw()))
def test_missing_key_rejects_the_reply(key):
    raw = valid_raw()
    del raw[key]
    with pytest.raises(InvalidResponseError):
        parse(raw)


@pytest.mark.parametrize("raw", [None, [], "text", 3])
def test_reply_that_is_not_an_object_is_rejected(raw):
    with pytest.raises(InvalidResponseError):
        parse(raw)


def test_naive_fetch_time_is_rejected():
    with pytest.raises(InvalidResponseError):
        PARSER.parse(valid_raw(), AIStatus.LIVE, datetime(2026, 11, 13))


def test_conflicting_sources_true_is_kept():
    assert parse(valid_raw(conflicting_sources=True)).conflicting_sources is True
