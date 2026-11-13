from datetime import datetime, timedelta
import pytest
from helpers import PORTS as DATA_PORTS, saved_record
from logic_fixtures import NOW, PORTS, FakeHistory, assessment, factor, insight, shipment
from data_layer.json_data_manager import JsonDataManager
from logic_layer.ai_insight_rule import AIInsightRule
from logic_layer.data_quality_rule import DataQualityRule
from logic_layer.insurance_rule import InsuranceRule
from logic_layer.logic_manager import LogicManager
from logic_layer.perfect_storm_rule import PerfectStormRule
from logic_layer.procurement_rule import ProcurementRule
from logic_layer.route_history_rule import RouteHistoryRule
from logic_layer.rule_config import RuleConfig
from logic_layer.unregistered_location_rule import UnregisteredLocationRule
from model.ai_assessment import AIAssessment
from model.shipment_record import ShipmentRecord
from model.flag import Flag
from model.outcome import Outcome
from model.risk_level import RiskLevel
from model.risk_type import RiskType


def manager(history=None, config=None):
    return LogicManager(history or FakeHistory(), PORTS, config)


def test_rules_run_in_the_agreed_order():
    assert [type(r) for r in manager().rules] == [
        DataQualityRule, PerfectStormRule, AIInsightRule, InsuranceRule,
        UnregisteredLocationRule, RouteHistoryRule, ProcurementRule]


def test_the_default_config_is_used_when_none_is_given():
    assert manager().config.to_dict() == RuleConfig().to_dict()


def test_a_clean_low_shipment_proceeds():
    d = manager().evaluate(shipment(), assessment(), NOW)
    assert d.shipment_id == "SHP-001"
    assert d.outcome is Outcome.PROCEED
    assert not d.needs_human
    assert d.rationale[-1] == "Rule 3: no flagged or delayed shipments on this route in the last 21 days"


def test_a_perfect_storm_is_delayed_for_a_human():
    a = assessment([factor(RiskType.WEATHER), factor(RiskType.PORT_CONGESTION), factor(RiskType.LABOR_SHORTAGE)])
    d = manager().evaluate(shipment(), a, NOW)
    assert d.risk_level is RiskLevel.HIGH
    assert d.outcome is Outcome.DELAY
    assert d.has_flag(Flag.PERFECT_STORM) and d.needs_human


def test_an_extreme_factor_is_rejected():
    d = manager().evaluate(shipment(), assessment([factor(RiskType.GEOPOLITICAL, RiskLevel.EXTREME)]), NOW)
    assert d.outcome is Outcome.REJECT
    assert d.needs_human
    assert "Do not ship: extreme risk on this route" in d.actions


def test_an_extreme_multiple_risks_insight_is_rejected():
    d = manager().evaluate(shipment(), assessment(insights=[insight("MULTIPLE_RISKS", RiskLevel.EXTREME)]), NOW)
    assert d.risk_level is RiskLevel.EXTREME
    assert d.outcome is Outcome.REJECT


def test_piracy_is_insured():
    d = manager().evaluate(shipment(), assessment([factor(RiskType.PIRACY_THREAT, RiskLevel.LOW)]), NOW)
    assert d.outcome is Outcome.INSURE
    assert d.hold_shipment and d.needs_human


def test_a_fallback_assessment_escalates_to_a_human():
    d = manager().evaluate(shipment(), AIAssessment.fallback(NOW), NOW)
    assert d.has_flag(Flag.AI_UNAVAILABLE)
    assert d.outcome is Outcome.ESCALATE


def test_a_long_delay_insight_with_a_medium_factor_is_high():
    a = assessment([factor(RiskType.WEATHER)], [insight("POTENTIAL_DELAY", days=8)])
    d = manager().evaluate(shipment(), a, NOW)
    assert d.risk_level is RiskLevel.HIGH
    assert d.has_flag(Flag.SIGNIFICANT_DELAY)


def test_a_failing_rule_becomes_a_rule_error_and_the_others_still_run(caplog):
    history = FakeHistory(error=RuntimeError("boom"))
    a = assessment(location="SGSIN", impact="Cargo Destruction")
    d = manager(history).evaluate(shipment(), a, NOW)
    assert d.has_flag(Flag.RULE_ERROR)
    assert any("RouteHistoryRule could not run (boom)" in r for r in d.rationale)
    assert d.has_flag(Flag.PROCUREMENT_ALERT)      # the rule after it still ran
    assert d.needs_human
    assert d.outcome is Outcome.DELAY
    assert "RouteHistoryRule failed on SHP-001" in caplog.text


def test_route_history_comes_from_the_data_manager(tmp_path):
    data = JsonDataManager(tmp_path / "records.json", DATA_PORTS)
    data.save(saved_record("SHP-001", outcome="DELAY", saved_at=NOW - timedelta(days=2)))
    d = LogicManager(data, PORTS).evaluate(shipment("SHP-002"), assessment(), NOW)
    assert d.has_flag(Flag.CAUTIONARY_OVERRIDE)
    assert d.outcome is Outcome.ESCALATE


def test_update_config_rebuilds_the_rules():
    logic = manager()
    a = assessment(confidence=0.7)
    assert not logic.evaluate(shipment(), a, NOW).has_flag(Flag.LOW_CONFIDENCE)
    logic.update_config(RuleConfig(confidence_min=0.8))
    assert logic.config.confidence_min == 0.8
    assert logic.evaluate(shipment(), a, NOW).has_flag(Flag.LOW_CONFIDENCE)


def test_update_config_needs_a_rule_config():
    with pytest.raises(TypeError):
        manager().update_config({"confidence_min": 0.8})


def test_now_must_be_timezone_aware():
    with pytest.raises(ValueError):
        manager().evaluate(shipment(), assessment(), datetime(2026, 11, 13, 9, 0))


def evaluate_and_save(logic, data, shipment_id, when):
    """Evaluate a clean Low shipment at a given time and save it the way main.assess_shipments does."""
    a = assessment(fetched_at=when)
    d = logic.evaluate(shipment(shipment_id), a, when)
    data.save(ShipmentRecord(shipment(shipment_id), a, d, when))
    return d


def test_a_cautionary_override_does_not_feed_itself(tmp_path):
    data = JsonDataManager(tmp_path / "records.json", DATA_PORTS)
    start = NOW - timedelta(days=30)
    data.save(saved_record("SHP-001", risk="MEDIUM", saved_at=start))
    logic = LogicManager(data, PORTS)
    first = evaluate_and_save(logic, data, "SHP-002", start + timedelta(days=15))
    assert first.has_flag(Flag.CAUTIONARY_OVERRIDE) and first.needs_human    # the real Medium is 15 days old
    second = evaluate_and_save(logic, data, "SHP-003", start + timedelta(days=30))
    assert not second.has_flag(Flag.CAUTIONARY_OVERRIDE)                     # only the override is in the window
    assert second.outcome is Outcome.PROCEED


def test_two_clean_low_shipments_in_a_row_both_proceed(tmp_path):
    data = JsonDataManager(tmp_path / "records.json", DATA_PORTS)
    logic = LogicManager(data, PORTS)
    evaluate_and_save(logic, data, "SHP-001", NOW - timedelta(days=15))
    second = evaluate_and_save(logic, data, "SHP-002", NOW)
    assert not second.has_flag(Flag.CAUTIONARY_OVERRIDE)
    assert second.outcome is Outcome.PROCEED


class BrokenStormConfig(RuleConfig):
    """A config whose storm threshold cannot be read, so PerfectStormRule fails."""

    @property
    def perfect_storm_min_mediums(self):
        raise RuntimeError("storm setting broken")


def test_a_failing_early_rule_still_lets_later_rules_and_the_resolver_run():
    a = assessment([factor(RiskType.PIRACY_THREAT, RiskLevel.LOW)], [insight("POTENTIAL_DELAY", days=4)])
    d = manager(config=BrokenStormConfig()).evaluate(shipment(), a, NOW)
    assert d.has_flag(Flag.RULE_ERROR)
    assert any("PerfectStormRule could not run (storm setting broken)" in r for r in d.rationale)
    assert d.has_flag(Flag.SIGNIFICANT_DELAY)       # AIInsightRule ran
    assert d.has_flag(Flag.PREMIUM_INCREASE)        # InsuranceRule ran
    assert d.outcome is Outcome.INSURE              # the resolver ran
    assert d.actions[-1] == "Route to human review queue"
