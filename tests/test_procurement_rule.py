import pytest
from logic_fixtures import NOW, assessment, decision, shipment
from logic_layer.procurement_rule import ProcurementRule
from model.flag import Flag


def run(a):
    d = decision()
    ProcurementRule().apply(shipment(), a, d, NOW)
    return d


def test_destruction_at_the_origin_alerts_procurement():
    d = run(assessment(location="SGSIN", impact="Cargo Destruction"))
    assert d.hold_shipment
    assert d.has_flag(Flag.PROCUREMENT_ALERT)
    assert d.actions == ("Reorder goods immediately: the goods on this shipment",)
    alert = d.alerts[0]
    assert alert["recipient"] == "procurement_team" and alert["channels"] == ["email"]
    assert "SHP-001" in alert["message"] and "Singapore" in alert["message"]


def test_destruction_elsewhere_changes_nothing():
    d = run(assessment(location="NLRTM", impact="Cargo Destruction"))
    assert not d.hold_shipment and d.alerts == ()


def test_other_impacts_at_the_origin_change_nothing():
    d = run(assessment(location="SGSIN", impact="Delay"))
    assert not d.hold_shipment and d.flags == ()


@pytest.mark.parametrize("location", ["sgsin", " SGSIN", "SGSIN - Singapore, SG"])
def test_the_origin_is_matched_loosely(location):
    d = run(assessment(location=location, impact="Cargo Destruction"))
    assert d.has_flag(Flag.PROCUREMENT_ALERT)


def test_another_port_label_does_not_match():
    d = run(assessment(location="NLRTM - Rotterdam, NL", impact="Cargo Destruction"))
    assert not d.has_flag(Flag.PROCUREMENT_ALERT)
