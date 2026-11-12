from logic_fixtures import NOW, assessment, decision, insight, shipment
from logic_layer.ai_insight_rule import AIInsightRule
from logic_layer.rule_config import RuleConfig
from model.flag import Flag
from model.risk_level import RiskLevel


def run(insights, config=None):
    d = decision()
    AIInsightRule(config or RuleConfig()).apply(shipment(), assessment(insights=insights), d, NOW)
    return d


def test_no_insights_change_nothing():
    d = run([])
    assert d.risk_level is RiskLevel.LOW and not d.needs_human and d.rationale == ()


def test_a_data_quality_code_needs_a_human():
    d = run([insight("MISSING_DATA")])
    assert d.has_flag(Flag.AI_FLAGGED)
    assert d.needs_human
    assert "MISSING_DATA" in d.rationale[0]


def test_a_short_delay_changes_nothing():
    d = run([insight("POTENTIAL_DELAY", days=2)])
    assert d.risk_level is RiskLevel.LOW
    assert not d.has_flag(Flag.SIGNIFICANT_DELAY)


def test_a_delay_at_the_limit_is_medium():
    d = run([insight("POTENTIAL_DELAY", days=3)])
    assert d.risk_level is RiskLevel.MEDIUM
    assert d.has_flag(Flag.SIGNIFICANT_DELAY)


def test_a_delay_at_the_high_limit_is_high():
    d = run([insight("POTENTIAL_DELAY", days=7)])
    assert d.risk_level is RiskLevel.HIGH


def test_only_the_worst_delay_counts():
    d = run([insight("POTENTIAL_DELAY", days=4), insight("POTENTIAL_DELAY", days=9)])
    assert d.risk_level is RiskLevel.HIGH
    assert len(d.rationale) == 1
    assert "+9d" in d.rationale[0]


def test_delay_limits_come_from_the_config():
    d = run([insight("POTENTIAL_DELAY", days=2)], RuleConfig(delay_days_limit=1, delay_days_high=2))
    assert d.risk_level is RiskLevel.HIGH


def test_high_or_extreme_multiple_risks_is_compound_risk_at_that_level():
    for severity in (RiskLevel.HIGH, RiskLevel.EXTREME):
        d = run([insight("MULTIPLE_RISKS", severity)])
        assert d.risk_level is severity
        assert d.has_flag(Flag.COMPOUND_RISK)
        assert d.rationale[0].endswith(f"-> risk {severity.label}")


def test_medium_multiple_risks_changes_nothing():
    d = run([insight("MULTIPLE_RISKS", RiskLevel.MEDIUM)])
    assert d.risk_level is RiskLevel.LOW
    assert not d.has_flag(Flag.COMPOUND_RISK)


def test_describe_shows_code_type_severity_place_and_days():
    assert AIInsightRule.describe(insight("POTENTIAL_DELAY", RiskLevel.HIGH, 8, "CNSHA")) == \
        "POTENTIAL_DELAY weather/High @CNSHA +8d"
