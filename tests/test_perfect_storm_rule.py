from logic_fixtures import NOW, assessment, decision, factor, shipment
from logic_layer.perfect_storm_rule import PerfectStormRule
from logic_layer.rule_config import RuleConfig
from model.flag import Flag
from model.risk_level import RiskLevel
from model.risk_type import RiskType


def run(factors, config=None):
    d = decision()
    PerfectStormRule(config or RuleConfig()).apply(shipment(), assessment(factors), d, NOW)
    return d


def test_no_factors_stay_low():
    d = run([])
    assert d.risk_level is RiskLevel.LOW
    assert d.rationale == ()


def test_a_high_factor_raises_the_risk_to_high():
    d = run([factor(RiskType.GEOPOLITICAL, RiskLevel.HIGH)])
    assert d.risk_level is RiskLevel.HIGH
    assert not d.has_flag(Flag.PERFECT_STORM)


def test_an_extreme_factor_stays_extreme():
    d = run([factor(RiskType.GEOPOLITICAL, RiskLevel.EXTREME), factor(RiskType.WEATHER, RiskLevel.HIGH)])
    assert d.risk_level is RiskLevel.EXTREME


def test_three_medium_storm_factors_make_a_perfect_storm():
    d = run([factor(RiskType.WEATHER), factor(RiskType.PORT_CONGESTION), factor(RiskType.LABOR_SHORTAGE)])
    assert d.risk_level is RiskLevel.HIGH
    assert d.has_flag(Flag.PERFECT_STORM)


def test_storm_factors_above_medium_also_count():
    d = run([factor(RiskType.WEATHER, RiskLevel.HIGH), factor(RiskType.PORT_CONGESTION),
             factor(RiskType.LABOR_SHORTAGE, RiskLevel.EXTREME)])
    assert d.has_flag(Flag.PERFECT_STORM)
    assert d.risk_level is RiskLevel.EXTREME


def test_two_storm_factors_are_only_medium():
    d = run([factor(RiskType.WEATHER), factor(RiskType.PORT_CONGESTION)])
    assert d.risk_level is RiskLevel.MEDIUM
    assert not d.has_flag(Flag.PERFECT_STORM)


def test_the_same_type_twice_counts_once():
    d = run([factor(RiskType.WEATHER), factor(RiskType.WEATHER), factor(RiskType.PORT_CONGESTION)])
    assert not d.has_flag(Flag.PERFECT_STORM)


def test_non_storm_factors_do_not_count_towards_the_storm():
    d = run([factor(RiskType.WEATHER), factor(RiskType.PORT_CONGESTION), factor(RiskType.GEOPOLITICAL)])
    assert not d.has_flag(Flag.PERFECT_STORM)


def test_the_storm_threshold_comes_from_the_config():
    d = run([factor(RiskType.WEATHER), factor(RiskType.PORT_CONGESTION)], RuleConfig(perfect_storm_min_mediums=2))
    assert d.has_flag(Flag.PERFECT_STORM)


def test_low_factors_leave_the_risk_low():
    d = run([factor(RiskType.WEATHER, RiskLevel.LOW)])
    assert d.risk_level is RiskLevel.LOW
