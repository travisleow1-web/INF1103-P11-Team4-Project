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


def test_apply_records_the_suggestion_with_its_reasoning_and_leaves_the_outcome_alone():
    d = decision()
    RULE.apply(shipment(), stormy(), d, NOW)
    assert d.actions == ("Consider departing on 05/12/2026 and arriving on 01/01/2027 instead of 01/12/2026",)
    assert d.reschedule["new_departure"] == "2026-12-05" and d.reschedule["new_arrival"] == "2027-01-01"
    assert d.rationale == ("Reschedule: " + d.reschedule["reasoning"],)
    assert d.outcome is Outcome.PROCEED and not d.needs_human and d.risk_level is RiskLevel.LOW


def test_the_reasoning_names_the_problem_the_better_date_and_the_new_arrival():
    d = decision()
    RULE.apply(shipment(), stormy(), d, NOW)
    why = d.reschedule["reasoning"]
    assert "Departing on 01/12/2026 meets High weather risk at SGSIN (test factor)" in why
    assert "clear weather window in the forecast starting 05/12/2026, 4 days later" in why
    assert "same 27-day journey" in why and "arrive on 01/01/2027 instead of 28/12/2026" in why


def test_only_a_weather_problem_justifies_a_new_date():
    piracy = assessment([factor(RiskType.PIRACY_THREAT, RiskLevel.HIGH)], primary=RiskType.PIRACY_THREAT)
    with_date = AIAssessment(piracy.risk_factors, piracy.insights, piracy.primary_risk_factor,
                             piracy.affected_location, piracy.expected_impact, piracy.confidence_score,
                             piracy.conflicting_sources, piracy.status, piracy.fetched_at, CLEAR)
    assert RULE.plan_for(shipment(), with_date, TODAY) is None


def test_apply_does_nothing_without_a_plan():
    d = decision()
    RULE.apply(shipment(), stormy(clear=None), d, NOW)
    assert d.actions == () and d.rationale == () and d.reschedule is None
