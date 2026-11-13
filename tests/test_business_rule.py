import pytest
from logic_layer.business_rule import BusinessRule
from logic_layer.insurance_rule import InsuranceRule


def test_business_rule_is_abstract():
    with pytest.raises(TypeError):
        BusinessRule()


def test_a_rule_is_named_after_its_class():
    assert InsuranceRule().name == "InsuranceRule"
