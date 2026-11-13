import pytest
from model.ai_status import AIStatus
from model.flag import Flag
from model.outcome import Outcome
from model.risk_level import RiskLevel
from model.risk_type import RiskType


def test_risk_levels_are_ordered():
    assert RiskLevel.LOW < RiskLevel.MEDIUM < RiskLevel.HIGH < RiskLevel.EXTREME
    assert max(RiskLevel.MEDIUM, RiskLevel.HIGH) is RiskLevel.HIGH


def test_risk_level_labels():
    assert [level.label for level in RiskLevel] == ["Low", "Medium", "High", "Extreme"]


@pytest.mark.parametrize("text", ["HIGH", "High", "high", " high "])
def test_parse_accepts_a_name_or_label_in_any_case(text):
    assert RiskLevel.parse(text) is RiskLevel.HIGH


def test_parse_accepts_a_risk_level():
    assert RiskLevel.parse(RiskLevel.EXTREME) is RiskLevel.EXTREME


@pytest.mark.parametrize("text", ["", "severe", "3", None, "Lowest"])
def test_parse_rejects_anything_else_instead_of_defaulting_to_low(text):
    with pytest.raises(ValueError):
        RiskLevel.parse(text)


def test_risk_type_values_match_the_ai_wording():
    assert RiskType("piracy_threat") is RiskType.PIRACY_THREAT
    assert RiskType.NONE.value == "none"
    assert len(RiskType) == 9


def test_outcome_and_status_values_are_their_names():
    assert [o.value for o in Outcome] == ["PROCEED", "DELAY", "INSURE", "ESCALATE", "REJECT"]
    assert [s.value for s in AIStatus] == ["LIVE", "CACHED", "FALLBACK"]


def test_string_enums_compare_equal_to_their_values():
    assert Outcome.DELAY == "DELAY"
    assert AIStatus("FALLBACK") is AIStatus.FALLBACK


def test_flags_keep_the_display_wording():
    assert Flag.PERFECT_STORM.value == "Perfect Storm"
    assert Flag("Route history unavailable") is Flag.ROUTE_HISTORY_UNAVAILABLE
    assert len(Flag) == 14


def test_an_unknown_value_is_an_error():
    with pytest.raises(ValueError):
        Outcome("REROUTE")
    with pytest.raises(ValueError):
        Flag("Stakeholder Alert")
