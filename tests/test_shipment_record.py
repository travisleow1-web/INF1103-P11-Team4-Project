from datetime import datetime
import pytest
from helpers import live_assessment, saved_record
from model.decision import Decision
from model.outcome import Outcome
from model.shipment_record import ShipmentRecord


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


def test_a_naive_saved_at_is_refused():
    shipment = saved_record().shipment
    with pytest.raises(ValueError):
        ShipmentRecord(shipment, live_assessment(), Decision("SHP-001"), datetime(2026, 11, 1, 9))


def test_saved_at_defaults_to_now_in_utc():
    record = ShipmentRecord(saved_record().shipment, live_assessment(), Decision("SHP-001"))
    assert record.saved_at.utcoffset().total_seconds() == 0
