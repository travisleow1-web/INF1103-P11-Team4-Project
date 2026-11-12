import pytest
from logic_fixtures import NOW, assessment, decision, factor, shipment
from logic_layer.insurance_rule import InsuranceRule
from model.flag import Flag
from model.risk_level import RiskLevel
from model.risk_type import RiskType


def run(a):
    d = decision()
    InsuranceRule().apply(shipment(), a, d, NOW)
    return d


@pytest.mark.parametrize("risk_type", [RiskType.PIRACY_THREAT, RiskType.SEVERE_CIVIL_UNREST])
def test_a_trigger_factor_holds_for_insurance(risk_type):
    d = run(assessment([factor(risk_type, RiskLevel.LOW)]))
    assert d.hold_shipment and d.needs_human
    assert d.risk_level is RiskLevel.HIGH
    assert d.has_flag(Flag.PREMIUM_INCREASE)
    assert d.actions == ("Update financial profile: extended insurance needed",)


def test_a_trigger_as_the_primary_risk_also_counts():
    d = run(assessment(primary=RiskType.PIRACY_THREAT))
    assert d.has_flag(Flag.PREMIUM_INCREASE)


def test_other_risks_change_nothing():
    d = run(assessment([factor(RiskType.WEATHER, RiskLevel.HIGH)], primary=RiskType.WEATHER))
    assert not d.hold_shipment and not d.needs_human
    assert d.risk_level is RiskLevel.LOW
