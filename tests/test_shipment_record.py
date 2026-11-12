from helpers import saved_record
from model.outcome import Outcome


def test_route_id_joins_the_port_codes():
    assert saved_record().shipment.route_id() == "SGSIN-NLRTM"


def test_a_low_risk_record_without_review_is_not_flagged():
    assert not saved_record(risk="LOW").is_flagged()


def test_risk_above_low_or_a_human_review_flags_a_record():
    assert saved_record(risk="MEDIUM").is_flagged()
    assert saved_record(risk="LOW", needs_human=True).is_flagged()


def test_only_a_delay_outcome_counts_as_delayed():
    assert saved_record(outcome=Outcome.DELAY.value).is_delayed()
    assert not saved_record(outcome="ESCALATE").is_delayed()
