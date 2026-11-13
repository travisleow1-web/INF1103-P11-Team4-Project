import pytest
from logic_layer.rule_config import RuleConfig


def test_defaults_match_jun_jies_values():
    config = RuleConfig()
    assert config.confidence_min == 0.60
    assert config.history_window_days == 21
    assert config.perfect_storm_min_mediums == 3
    assert config.data_max_age_hours == 24
    assert config.delay_days_limit == 3
    assert config.delay_days_high == 7


def test_overrides_replace_only_the_given_values():
    config = RuleConfig(confidence_min=0.5, history_window_days=7)
    assert config.confidence_min == 0.5
    assert config.history_window_days == 7
    assert config.delay_days_high == 7


def test_to_dict_and_from_dict_round_trip():
    config = RuleConfig(delay_days_limit=2, delay_days_high=5)
    again = RuleConfig.from_dict(config.to_dict())
    assert again.to_dict() == config.to_dict()


def test_to_dict_is_a_copy():
    config = RuleConfig()
    config.to_dict()["confidence_min"] = 0.1
    assert config.confidence_min == 0.60


def test_from_dict_fills_missing_keys_with_defaults():
    assert RuleConfig.from_dict({"history_window_days": 10}).perfect_storm_min_mediums == 3


@pytest.mark.parametrize("settings", [
    {"unknown_key": 1},
    {"confidence_min": 1.5},
    {"confidence_min": -0.1},
    {"confidence_min": True},
    {"confidence_min": "0.5"},
    {"history_window_days": 0},
    {"history_window_days": 2.5},
    {"data_max_age_hours": False},
    {"perfect_storm_min_mediums": 4},
    {"delay_days_limit": 5, "delay_days_high": 4},
])
def test_bad_settings_are_rejected(settings):
    with pytest.raises(ValueError):
        RuleConfig(**settings)


@pytest.mark.parametrize("data", [None, "confidence_min=0.5", [("confidence_min", 0.5)], 3, {1: 2}])
def test_from_dict_rejects_anything_but_a_mapping_of_settings(data):
    with pytest.raises(ValueError):
        RuleConfig.from_dict(data)


def test_the_defaults_cannot_be_changed_from_outside():
    assert not hasattr(RuleConfig, "DEFAULTS")
    RuleConfig().to_dict()["history_window_days"] = 99
    assert RuleConfig().history_window_days == 21
