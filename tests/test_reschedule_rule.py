from datetime import date
import pytest
from logic_fixtures import NOW, assessment, decision, factor, shipment
from logic_layer.reschedule_rule import RescheduleRule
from model.flag import Flag
from model.risk_level import RiskLevel
from model.risk_type import RiskType

CLEAR = date(2026, 12, 6)      # the fixture shipment departs 01/12/2026 and arrives 28/12/2026


def run(risk=RiskLevel.HIGH, clear=CLEAR):
    d = decision()
    d.raise_risk(risk)
    a = assessment([factor(severity=RiskLevel.HIGH)], primary=RiskType.PORT_CONGESTION, location="SGSIN",
                   clear_departure=clear)
    RescheduleRule().apply(shipment(), a, d, NOW)
    return d


@pytest.mark.parametrize("risk", [RiskLevel.HIGH, RiskLevel.EXTREME])
def test_high_risk_with_a_later_clear_window_suggests_new_dates(risk):
    d = run(risk)
    assert d.has_flag(Flag.RESCHEDULE_SUGGESTED)
    assert d.actions == ("Reschedule: depart 06/12/2026, arrive 02/01/2027",)     # same 27-day journey
    assert "port congestion @SGSIN" in d.rationale[0]


def test_reschedule_does_not_change_the_outcome_or_ask_for_a_human():
    d = run()
    assert not d.needs_human and not d.hold_shipment
    assert d.outcome.value == "PROCEED"         # the OutcomeResolver decides later


@pytest.mark.parametrize("risk", [RiskLevel.LOW, RiskLevel.MEDIUM])
def test_lower_risk_needs_no_reschedule(risk):
    assert run(risk).flags == ()


@pytest.mark.parametrize("clear", [None, date(2026, 12, 1), date(2026, 11, 20)])
def test_no_suggestion_without_a_clear_date_after_departure(clear):
    d = run(clear=clear)
    assert d.flags == () and d.actions == ()
