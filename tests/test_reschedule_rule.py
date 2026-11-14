from datetime import date, datetime, timedelta, timezone
import pytest
from logic_fixtures import NOW, assessment, decision, factor, shipment
from logic_layer.reschedule_rule import RescheduleRule
from model.ai_assessment import AIAssessment
from model.outcome import Outcome
from model.risk_level import RiskLevel
from model.risk_type import RiskType

TODAY = NOW.date()                      # 13/11/2026; the shipment leaves 01/12 and arrives 28/12 (27 days)
CLEAR = date(2026, 12, 5)
RULE = RescheduleRule()


def stormy(severity=RiskLevel.HIGH, clear=CLEAR):
    base = assessment([factor(RiskType.WEATHER, severity)], primary=RiskType.WEATHER, location="SGSIN",
                      impact="Delay")
    return AIAssessment(base.risk_factors, base.insights, base.primary_risk_factor, base.affected_location,
                        base.expected_impact, base.confidence_score, base.conflicting_sources, base.status,
                        base.fetched_at, clear)


def test_a_plan_keeps_the_journey_length():
    plan = RULE.plan_for(shipment(), stormy(), TODAY)
    assert plan.new_departure == CLEAR and plan.new_arrival == CLEAR + timedelta(days=27)
    assert plan.original_departure == date(2026, 12, 1) and plan.shipment_id == "SHP-001"
    assert plan.reason == "weather at SGSIN"


def test_extreme_risk_also_gets_a_plan():
    assert RULE.plan_for(shipment(), stormy(RiskLevel.EXTREME), TODAY) is not None


@pytest.mark.parametrize("severity", [RiskLevel.LOW, RiskLevel.MEDIUM])
def test_a_low_or_medium_risk_gets_no_plan(severity):
    assert RULE.plan_for(shipment(), stormy(severity), TODAY) is None


def test_no_date_from_the_ai_means_no_plan():
    assert RULE.plan_for(shipment(), stormy(clear=None), TODAY) is None


@pytest.mark.parametrize("clear", [date(2026, 12, 1), date(2026, 11, 20)])
def test_a_date_not_after_the_planned_departure_means_no_plan(clear):
    assert RULE.plan_for(shipment(), stormy(clear=clear), TODAY) is None


def test_a_shipment_that_already_left_gets_no_plan():
    assert RULE.plan_for(shipment(), stormy(), date(2026, 12, 2)) is None


def test_apply_adds_an_action_and_a_note_and_leaves_the_outcome_alone():
    d = decision()
    RULE.apply(shipment(), stormy(), d, NOW)
    assert d.actions == ("Consider departing on 05/12/2026 and arriving on 01/01/2027 instead of 01/12/2026",)
    assert d.rationale == ("Reschedule: weather at SGSIN, clear weather from 05/12/2026",)
    assert d.outcome is Outcome.PROCEED and not d.needs_human and d.risk_level is RiskLevel.LOW


def test_apply_does_nothing_without_a_plan():
    d = decision()
    RULE.apply(shipment(), stormy(clear=None), d, NOW)
    assert d.actions == () and d.rationale == ()
