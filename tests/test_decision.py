import pytest
from model.decision import Decision
from model.flag import Flag
from model.outcome import Outcome
from model.risk_level import RiskLevel


def test_a_new_decision_is_low_risk_and_proceeds():
    d = Decision("SHP-001")
    assert d.shipment_id == "SHP-001"
    assert d.risk_level is RiskLevel.LOW
    assert d.overall_risk == "Low"
    assert d.outcome is Outcome.PROCEED
    assert not d.hold_shipment and not d.needs_human
    assert d.flags == d.actions == d.alerts == d.rationale == ()


def test_risk_only_goes_up():
    d = Decision("SHP-001")
    d.raise_risk(RiskLevel.HIGH)
    d.raise_risk(RiskLevel.MEDIUM)
    assert d.risk_level is RiskLevel.HIGH
    d.raise_risk(RiskLevel.EXTREME)
    assert d.overall_risk == "Extreme"


def test_add_note_records_the_reason_flag_action_and_review():
    d = Decision("SHP-001")
    d.add_note("Three medium risks", Flag.PERFECT_STORM, "Hold at port", human=True)
    assert d.rationale == ("Three medium risks",)
    assert d.flags == (Flag.PERFECT_STORM,)
    assert d.actions == ("Hold at port",)
    assert d.needs_human
    assert d.has_flag(Flag.PERFECT_STORM)
    assert not d.has_flag(Flag.COMPOUND_RISK)


def test_a_flag_is_kept_once():
    d = Decision("SHP-001")
    d.add_note("first", Flag.COMPOUND_RISK)
    d.add_note("second", Flag.COMPOUND_RISK)
    assert d.flags == (Flag.COMPOUND_RISK,)
    assert len(d.rationale) == 2


def test_flags_must_be_known():
    with pytest.raises(ValueError):
        Decision("SHP-001").add_note("why", flag="Made-up flag")


def test_a_note_without_human_does_not_clear_an_earlier_request():
    d = Decision("SHP-001")
    d.require_human()
    d.add_note("fine")
    assert d.needs_human


def test_outcome_must_be_an_outcome():
    d = Decision("SHP-001")
    d.set_outcome(Outcome.DELAY)
    assert d.outcome is Outcome.DELAY
    with pytest.raises(ValueError):
        d.set_outcome("REROUTE")


def test_hold_actions_and_alerts():
    d = Decision("SHP-001")
    d.hold()
    d.add_action("Call the carrier")
    d.add_alert("Ops team", ("email",), "Shipment on hold")
    assert d.hold_shipment
    assert d.actions == ("Call the carrier",)
    assert d.alerts == ({"recipient": "Ops team", "channels": ["email"], "message": "Shipment on hold"},)


def test_returned_collections_cannot_change_the_decision():
    d = Decision("SHP-001")
    d.add_alert("Ops team", ["email"], "hello")
    d.alerts[0]["channels"].append("sms")
    d.to_dict()["flags"].append("x")
    assert d.alerts[0]["channels"] == ["email"]
    assert d.to_dict()["flags"] == []


def full_decision():
    d = Decision("SHP-007")
    d.raise_risk(RiskLevel.HIGH)
    d.set_outcome(Outcome.ESCALATE)
    d.hold()
    d.add_note("Storm and congestion", Flag.PERFECT_STORM, "Hold at port", human=True)
    d.add_note("Premium up", Flag.PREMIUM_INCREASE)
    d.add_alert("Insurer", ["email"], "Premium review")
    return d


def test_to_dict_uses_the_label_and_enum_values():
    assert full_decision().to_dict() == {
        "shipment_id": "SHP-007", "overall_risk": "High", "outcome": "ESCALATE",
        "hold_shipment": True, "needs_human": True,
        "flags": ["Perfect Storm", "Premium Increase Required"],
        "actions": ["Hold at port"],
        "alerts": [{"recipient": "Insurer", "channels": ["email"], "message": "Premium review"}],
        "rationale": ["Storm and congestion", "Premium up"],
    }


def test_round_trip_keeps_everything():
    original = full_decision()
    copy = Decision.from_dict(original.to_dict())
    assert copy.to_dict() == original.to_dict()
    assert copy.risk_level is RiskLevel.HIGH
    assert copy.outcome is Outcome.ESCALATE
    assert copy.flags == (Flag.PERFECT_STORM, Flag.PREMIUM_INCREASE)


@pytest.mark.parametrize("change", [{"overall_risk": "Severe"}, {"outcome": "REROUTE"}, {"flags": ["Nope"]}])
def test_from_dict_rejects_bad_values(change):
    with pytest.raises(ValueError):
        Decision.from_dict({**full_decision().to_dict(), **change})


def test_from_dict_rejects_a_missing_key():
    data = full_decision().to_dict()
    del data["rationale"]
    with pytest.raises(KeyError):
        Decision.from_dict(data)
