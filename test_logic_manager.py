"""
test_logic_manager.py - automated tests for the Logic Manager.

Uses hard-coded sample AI responses and a fake route-history source,
so no live AI API, files or database are needed.

Run:  python -m unittest test_logic_manager -v
"""

import unittest
from datetime import datetime, timedelta

from logic_manager import (BusinessRule, Decision, InvalidRecordError, LogicManager, RiskLevel,
                           RouteHistorySource, RuleConfig)
from logic.recordpreparer import RecordPreparer

NOW = datetime(2026, 11, 9, 12, 0)

class FakeHistory(RouteHistorySource):
    """Stands in for the Data Manager."""

    def __init__(self, runs=None, error=None):
        self._runs = runs or []
        self._error = error

    def get_route_history(self, route_id, since):
        if self._error:
            raise self._error
        return [r for r in self._runs if r["route_id"] == route_id and r["date"] >= since]


def sample_record(**changes):
    """A clean, low-risk AI response; tests change only the fields they care about."""
    record = {
        "shipment_id": "SHP-001", "origin_port": "SGSIN", "destination_port": "NLRTM",
        "risk_factors": [{"type": "weather", "severity": "Low"}],
        "primary_risk_factor": "weather", "affected_location": "CNSHA",
        "expected_impact": "Delay", "confidence_score": 0.85, "sources": ["MPA advisory"],
        "insights": [], "external_data_fetched_at": (NOW - timedelta(hours=2)).isoformat(),
        "conflicting_sources": False,
    }
    record.update(changes)
    return record


def evaluate(record, history=None, config=None):
    manager = LogicManager(history or FakeHistory(), config=config)
    return manager.evaluate_shipment(record, NOW)[1]


class TestValidation(unittest.TestCase):
    def test_missing_field_is_rejected(self):
        record = sample_record()
        del record["expected_impact"]
        decision = evaluate(record)
        self.assertEqual(decision.outcome, "REJECT")
        self.assertIn("Incomplete AI record", decision.flags)

    def test_confidence_outside_0_to_1_is_rejected(self):
        for bad in (1.5, -0.1, "high", True):
            with self.subTest(confidence=bad):
                self.assertEqual(evaluate(sample_record(confidence_score=bad)).outcome, "REJECT")

    def test_low_confidence_goes_to_human(self):
        decision = evaluate(sample_record(confidence_score=0.4))
        self.assertIn("Low AI confidence", decision.flags)
        self.assertEqual(decision.outcome, "ESCALATE")

    def test_outdated_data_goes_to_human(self):
        old = (NOW - timedelta(hours=30)).isoformat()
        self.assertIn("Outdated external data", evaluate(sample_record(external_data_fetched_at=old)).flags)

    def test_malformed_list_items_are_dropped_and_flagged(self):
        decision = evaluate(sample_record(risk_factors=[{"type": "weather"}, "junk"]))
        self.assertIn("Malformed AI items dropped", decision.flags)
        self.assertTrue(decision.needs_human)

    def test_conflicting_sources_go_to_human(self):
        self.assertIn("Conflicting sources", evaluate(sample_record(conflicting_sources=True)).flags)

    def test_rejected_record_skips_the_rules(self):
        record = sample_record(primary_risk_factor="piracy_threat", confidence_score=2)
        decision = evaluate(record)
        self.assertEqual(decision.outcome, "REJECT")
        self.assertNotIn("Premium Increase Required", decision.flags)


class TestRules(unittest.TestCase):
    def test_clean_low_risk_route_proceeds(self):
        decision = evaluate(sample_record())
        self.assertEqual(decision.outcome, "PROCEED")
        self.assertEqual(decision.overall_risk, "Low")
        self.assertFalse(decision.needs_human)

    def test_perfect_storm_upgrades_three_mediums_to_high(self):
        factors = [{"type": t, "severity": "Medium"} for t in ("weather", "port_congestion", "labor_shortage")]
        decision = evaluate(sample_record(risk_factors=factors))
        self.assertEqual(decision.overall_risk, "High")
        self.assertIn("Perfect Storm", decision.flags)
        self.assertEqual(decision.outcome, "DELAY")

    def test_two_mediums_stay_medium(self):
        factors = [{"type": t, "severity": "Medium"} for t in ("weather", "port_congestion")]
        decision = evaluate(sample_record(risk_factors=factors))
        self.assertEqual(decision.overall_risk, "Medium")
        self.assertEqual(decision.outcome, "PROCEED")
        self.assertIn("Proceed with monitoring", decision.actions)

    def test_delay_insights_raise_risk_by_days(self):
        for days, expected in ((2, "Low"), (3, "Medium"), (7, "High")):
            insight = {"code": "POTENTIAL_DELAY", "risk_type": "weather", "severity": "Medium",
                       "location": "CNSHA", "estimated_delay_days": days}
            with self.subTest(days=days):
                self.assertEqual(evaluate(sample_record(insights=[insight])).overall_risk, expected)

    def test_missing_data_insight_goes_to_human(self):
        insight = {"code": "MISSING_DATA", "risk_type": "weather", "severity": "Low",
                   "location": "SGSIN", "estimated_delay_days": 0}
        decision = evaluate(sample_record(insights=[insight]))
        self.assertIn("AI flagged: MISSING_DATA", decision.flags)
        self.assertEqual(decision.outcome, "ESCALATE")

    def test_piracy_needs_insurance(self):
        decision = evaluate(sample_record(primary_risk_factor="piracy_threat"))
        self.assertEqual(decision.outcome, "INSURE")
        self.assertTrue(decision.hold_shipment)
        self.assertEqual(decision.overall_risk, "High")

    def test_low_route_with_recent_delay_is_escalated(self):
        history = FakeHistory([{"route_id": "SGSIN-NLRTM", "date": NOW - timedelta(days=5), "delayed": True}])
        decision = evaluate(sample_record(), history)
        self.assertIn("Cautionary Override", decision.flags)
        self.assertEqual(decision.outcome, "ESCALATE")

    def test_old_delay_outside_window_is_ignored(self):
        history = FakeHistory([{"route_id": "SGSIN-NLRTM", "date": NOW - timedelta(days=40), "delayed": True}])
        self.assertEqual(evaluate(sample_record(), history).outcome, "PROCEED")

    def test_unreadable_history_goes_to_human(self):
        decision = evaluate(sample_record(), FakeHistory(error=KeyError("route_id")))
        self.assertIn("Route history unavailable", decision.flags)
        self.assertEqual(decision.outcome, "ESCALATE")

    def test_cargo_destruction_at_origin_triggers_procurement(self):
        decision = evaluate(sample_record(expected_impact="Cargo Destruction", affected_location="SGSIN"))
        self.assertEqual(decision.outcome, "DELAY")
        self.assertIn("Procurement Alert", decision.flags)
        self.assertEqual(decision.alerts[0]["recipient"], "procurement_team")
        self.assertEqual(decision.alerts[0]["channels"], ["email"])

    def test_cargo_destruction_elsewhere_is_not_procurement(self):
        decision = evaluate(sample_record(expected_impact="Cargo Destruction", affected_location="CNSHA"))
        self.assertNotIn("Procurement Alert", decision.flags)


class TestDesign(unittest.TestCase):
    def test_business_rule_cannot_be_created_directly(self):
        with self.assertRaises(TypeError):
            BusinessRule()

    def test_new_rule_can_be_added_without_changing_logic_manager(self):
        class AlwaysHoldRule(BusinessRule):  # OCP / LSP: any subclass works in the rule list
            def apply(self, record, decision, now):
                decision.hold()

        manager = LogicManager(FakeHistory())
        manager._rules.append(AlwaysHoldRule())
        self.assertEqual(manager.evaluate_shipment(sample_record(), NOW)[1].outcome, "ESCALATE")

    def test_risk_never_goes_down(self):
        decision = Decision("X")
        decision.raise_risk(RiskLevel.HIGH)
        decision.raise_risk(RiskLevel.LOW)
        self.assertEqual(decision.overall_risk, "High")

    def test_decision_rejects_unknown_outcome(self):
        with self.assertRaises(ValueError):
            Decision("X").set_outcome("MAYBE")

    def test_to_dict_has_the_fields_other_managers_use(self):
        keys = set(evaluate(sample_record()).to_dict())
        self.assertEqual(keys, {"shipment_id", "overall_risk", "outcome", "hold_shipment", "needs_human",
                                "flags", "actions", "alerts", "rationale"})

    def test_caller_record_is_not_modified(self):
        record = sample_record(insights=[{"code": "POTENTIAL_DELAY", "risk_type": "weather", "severity": "Low",
                                          "location": "CNSHA", "estimated_delay_days": "4"}])
        evaluate(record)
        self.assertEqual(record["insights"][0]["estimated_delay_days"], "4")


class TestRecordPreparer(unittest.TestCase):
    def test_missing_field_raises_invalid_record_error(self):
        preparer = RecordPreparer()
        record = preparer.prepare(sample_record(shipment_id=""))
        with self.assertRaises(InvalidRecordError) as ctx:
            preparer.ensure_usable(record)
        self.assertEqual(ctx.exception.flag, "Incomplete AI record")

    def test_route_id_is_built_from_ports(self):
        self.assertEqual(RecordPreparer().prepare(sample_record())["route_id"], "SGSIN-NLRTM")


class TestRuleConfig(unittest.TestCase):
    def test_custom_threshold_changes_the_outcome(self):
        insight = {"code": "POTENTIAL_DELAY", "risk_type": "weather", "severity": "Medium",
                   "location": "CNSHA", "estimated_delay_days": 5}
        self.assertEqual(evaluate(sample_record(insights=[insight])).overall_risk, "Medium")
        strict = RuleConfig(delay_days_high=5)
        self.assertEqual(evaluate(sample_record(insights=[insight]), config=strict).overall_risk, "High")

    def test_update_config_applies_new_values(self):
        manager = LogicManager(FakeHistory())
        manager.update_config(RuleConfig(confidence_min=0.9))
        decision = manager.evaluate_shipment(sample_record(confidence_score=0.85), NOW)[1]
        self.assertIn("Low AI confidence", decision.flags)

    def test_invalid_settings_are_refused(self):
        for bad in ({"confidence_min": 1.5}, {"history_window_days": 0}, {"delay_days_high": 2},
                    {"perfect_storm_min_mediums": 4}, {"not_a_setting": 1}):
            with self.subTest(settings=bad):
                with self.assertRaises(ValueError):
                    RuleConfig(**bad)

    def test_config_round_trips_through_dict(self):
        config = RuleConfig(confidence_min=0.7, history_window_days=14)
        self.assertEqual(RuleConfig.from_dict(config.to_dict()).to_dict(), config.to_dict())


class TestBatch(unittest.TestCase):
    def test_one_broken_row_does_not_stop_the_batch(self):
        manager = LogicManager(FakeHistory())
        rows = [sample_record(shipment_id="A"), sample_record(shipment_id="B", risk_factors=None,
                                                              primary_risk_factor=None), sample_record(shipment_id="C")]
        results = manager.evaluate_shipments(rows, NOW)
        self.assertEqual([d.outcome for _, d in results], ["PROCEED", "REJECT", "PROCEED"])


if __name__ == "__main__":
    unittest.main()
