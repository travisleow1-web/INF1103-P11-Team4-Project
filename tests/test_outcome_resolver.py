from logic_fixtures import decision
from logic_layer.outcome_resolver import OutcomeResolver
from model.flag import Flag
from model.outcome import Outcome
from model.risk_level import RiskLevel


def resolve(d):
    OutcomeResolver().resolve(d)
    return d


def test_low_risk_proceeds_with_no_actions():
    d = resolve(decision())
    assert d.outcome is Outcome.PROCEED
    assert d.actions == () and not d.needs_human


def test_medium_risk_proceeds_with_monitoring():
    d = decision()
    d.raise_risk(RiskLevel.MEDIUM)
    resolve(d)
    assert d.outcome is Outcome.PROCEED
    assert d.actions == ("Proceed with monitoring",)


def test_high_risk_delays_and_needs_a_human():
    d = decision()
    d.raise_risk(RiskLevel.HIGH)
    resolve(d)
    assert d.outcome is Outcome.DELAY
    assert d.needs_human
    assert d.actions == ("Delay departure until conditions clear", "Route to human review queue")


def test_extreme_risk_is_rejected_before_any_flag():
    d = decision()
    d.raise_risk(RiskLevel.EXTREME)
    d.add_note("procurement", Flag.PROCUREMENT_ALERT)
    d.add_note("insurance", Flag.PREMIUM_INCREASE, human=True)
    d.hold()
    resolve(d)
    assert d.outcome is Outcome.REJECT
    assert d.actions[-1] == "Route to human review queue"


def test_extreme_risk_alone_is_rejected_for_a_human_with_a_clear_action():
    d = decision()
    d.raise_risk(RiskLevel.EXTREME)
    resolve(d)
    assert d.outcome is Outcome.REJECT
    assert d.needs_human
    assert d.actions == ("Do not ship: extreme risk on this route", "Route to human review queue")


def test_procurement_alert_delays_before_insurance():
    d = decision()
    d.raise_risk(RiskLevel.HIGH)
    d.add_note("procurement", Flag.PROCUREMENT_ALERT)
    d.add_note("insurance", Flag.PREMIUM_INCREASE)
    resolve(d)
    assert d.outcome is Outcome.DELAY
    assert "Delay departure until conditions clear" not in d.actions


def test_premium_increase_insures_even_when_high():
    d = decision()
    d.raise_risk(RiskLevel.HIGH)
    d.add_note("insurance", Flag.PREMIUM_INCREASE)
    assert resolve(d).outcome is Outcome.INSURE


def test_a_held_low_shipment_escalates():
    d = decision()
    d.hold()
    resolve(d)
    assert d.outcome is Outcome.ESCALATE
    assert not d.needs_human


def test_a_low_shipment_needing_a_human_escalates_to_the_queue():
    d = decision()
    d.require_human()
    resolve(d)
    assert d.outcome is Outcome.ESCALATE
    assert d.actions == ("Route to human review queue",)
