from datetime import timedelta
from logic_fixtures import NOW, assessment, decision, shipment
from logic_layer.data_quality_rule import DataQualityRule
from logic_layer.rule_config import RuleConfig
from model.ai_assessment import AIAssessment
from model.flag import Flag


def run(a, config=None):
    d = decision()
    DataQualityRule(config or RuleConfig()).apply(shipment(), a, d, NOW)
    return d


def test_a_clean_assessment_changes_nothing():
    d = run(assessment())
    assert d.flags == () and not d.needs_human


def test_a_fallback_is_ai_unavailable_and_nothing_else():
    d = run(AIAssessment.fallback(NOW - timedelta(days=3)))
    assert d.flags == (Flag.AI_UNAVAILABLE,)
    assert d.needs_human


def test_low_confidence_needs_a_human():
    d = run(assessment(confidence=0.59))
    assert d.flags == (Flag.LOW_CONFIDENCE,)
    assert d.needs_human


def test_confidence_at_the_minimum_is_fine():
    assert run(assessment(confidence=0.60)).flags == ()


def test_the_confidence_minimum_comes_from_the_config():
    assert run(assessment(confidence=0.7), RuleConfig(confidence_min=0.8)).has_flag(Flag.LOW_CONFIDENCE)


def test_old_data_is_outdated():
    d = run(assessment(fetched_at=NOW - timedelta(hours=25)))
    assert d.flags == (Flag.OUTDATED_DATA,)
    assert d.needs_human


def test_data_exactly_at_the_age_limit_is_fine():
    assert run(assessment(fetched_at=NOW - timedelta(hours=24))).flags == ()


def test_conflicting_sources_need_a_human():
    d = run(assessment(conflicting=True))
    assert d.flags == (Flag.CONFLICTING_SOURCES,)
    assert d.needs_human


def test_every_problem_is_reported():
    d = run(assessment(confidence=0.1, conflicting=True, fetched_at=NOW - timedelta(days=2)))
    assert set(d.flags) == {Flag.LOW_CONFIDENCE, Flag.OUTDATED_DATA, Flag.CONFLICTING_SOURCES}
    assert len(d.rationale) == 3
