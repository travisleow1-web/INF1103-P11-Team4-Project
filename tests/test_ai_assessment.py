from datetime import datetime, timedelta, timezone
import pytest
from helpers import FETCHED_AT, live_assessment
from model.ai_assessment import AIAssessment
from model.ai_status import AIStatus
from model.insight import Insight
from model.risk_factor import RiskFactor
from model.risk_level import RiskLevel
from model.risk_type import RiskType


def an_insight():
    return Insight("POTENTIAL_DELAY", RiskType.WEATHER, RiskLevel.HIGH, "SGSIN", 4)


# RiskFactor and Insight

def test_risk_factor_dict_uses_the_type_value_and_severity_name():
    factor = RiskFactor(RiskType.PIRACY_THREAT, RiskLevel.HIGH, "Route", "gdelt_news", "Boarding reported")
    assert factor.to_dict() == {"type": "piracy_threat", "severity": "HIGH", "location": "Route",
                                "source": "gdelt_news", "detail": "Boarding reported"}
    assert RiskFactor.from_dict(factor.to_dict()) == factor


def test_risk_factor_severity_may_be_a_label():
    data = {"type": "weather", "severity": "Medium", "location": "SGSIN", "source": "x", "detail": ""}
    assert RiskFactor.from_dict(data).severity is RiskLevel.MEDIUM


@pytest.mark.parametrize("change", [{"type": "WEATHER"}, {"severity": "severe"}])
def test_risk_factor_rejects_unknown_values(change):
    data = {"type": "weather", "severity": "LOW", "location": "SGSIN", "source": "x", "detail": "", **change}
    with pytest.raises(ValueError):
        RiskFactor.from_dict(data)


def test_insight_round_trip():
    insight = an_insight()
    assert insight.to_dict()["risk_type"] == "weather"
    assert insight.to_dict()["severity"] == "HIGH"
    assert Insight.from_dict(insight.to_dict()) == insight


def test_model_values_cannot_be_changed():
    with pytest.raises(AttributeError):
        an_insight().code = "OTHER"


# AIAssessment

def test_properties_give_back_what_was_passed_with_lists_as_tuples():
    a = live_assessment()
    assert isinstance(a.risk_factors, tuple) and len(a.risk_factors) == 2
    assert a.insights == ()
    assert a.primary_risk_factor is RiskType.WEATHER
    assert a.affected_location == "SGSIN"
    assert a.expected_impact == "Delay"
    assert a.confidence_score == 0.8
    assert a.conflicting_sources is False
    assert a.status is AIStatus.LIVE
    assert a.fetched_at == FETCHED_AT
    assert not a.is_fallback()


def test_fallback_is_empty_and_marked():
    now = datetime(2026, 11, 13, 1, 2, tzinfo=timezone.utc)
    a = AIAssessment.fallback(now)
    assert a.is_fallback()
    assert a.to_dict() == {"risk_factors": [], "insights": [], "primary_risk_factor": "none",
                           "affected_location": "Unknown", "expected_impact": "None",
                           "confidence_score": 0.0, "conflicting_sources": False,
                           "ai_status": "FALLBACK", "fetched_at": "2026-11-13T01:02:00+00:00"}


def test_fallback_without_a_time_uses_now_in_utc():
    a = AIAssessment.fallback()
    assert a.fetched_at.tzinfo is not None
    assert datetime.now(timezone.utc) - a.fetched_at < timedelta(seconds=5)


def test_round_trip_keeps_everything():
    original = AIAssessment([], [an_insight()], RiskType.PORT_CONGESTION, "NLRTM", "Delay", 0.55, True,
                            AIStatus.CACHED, FETCHED_AT)
    copy = AIAssessment.from_dict(original.to_dict())
    assert copy.to_dict() == original.to_dict()
    assert copy.insights == original.insights
    assert copy.status is AIStatus.CACHED
    assert copy.fetched_at == FETCHED_AT


def test_from_dict_reads_a_naive_time_as_utc():
    data = live_assessment().to_dict()
    data["fetched_at"] = "2026-11-01T08:00:00"
    assert AIAssessment.from_dict(data).fetched_at == FETCHED_AT


def test_a_naive_fetch_time_is_refused():
    with pytest.raises(ValueError):
        AIAssessment([], [], RiskType.NONE, "Unknown", "None", 0.0, False, AIStatus.LIVE, datetime(2026, 11, 1))


@pytest.mark.parametrize("change", [{"ai_status": "BROKEN"}, {"primary_risk_factor": "aliens"},
                                    {"fetched_at": "yesterday"}])
def test_from_dict_rejects_bad_values(change):
    with pytest.raises(ValueError):
        AIAssessment.from_dict({**live_assessment().to_dict(), **change})


def test_from_dict_rejects_a_missing_key():
    data = live_assessment().to_dict()
    del data["insights"]
    with pytest.raises(KeyError):
        AIAssessment.from_dict(data)


def test_to_dict_returns_a_new_dict_each_time():
    a = live_assessment()
    a.to_dict()["risk_factors"].clear()
    assert len(a.to_dict()["risk_factors"]) == 2
