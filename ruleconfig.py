"""RuleConfig: all business-rule thresholds in one validated object (new feature)."""

from logic.riskrules import PerfectStormRule


class RuleConfig:
    """Every business-rule threshold in one validated object (new feature: user-configurable rules)."""

    _DEFAULTS = {
        "confidence_min": 0.60,           # below this, AI output needs a human
        "history_window_days": 21,        # Rule 3 look-back
        "perfect_storm_min_mediums": 3,   # Rule 1
        "data_max_age_hours": 24,         # external data older than this is "outdated"
        "delay_days_limit": 3,            # Rule 1b: delay that raises risk to Medium
        "delay_days_high": 7,             # Rule 1b: delay that raises risk to High
    }
    _WHOLE_NUMBER_KEYS = ("history_window_days", "perfect_storm_min_mediums",
                          "data_max_age_hours", "delay_days_limit", "delay_days_high")

    def __init__(self, **overrides):
        unknown = set(overrides) - set(self._DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown rule setting(s): {sorted(unknown)}")
        values = {**self._DEFAULTS, **overrides}
        self._validate(values)
        self._values = values

    @classmethod
    def _validate(cls, values):
        conf = values["confidence_min"]
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
            raise ValueError("confidence_min must be a number between 0 and 1")
        for key in cls._WHOLE_NUMBER_KEYS:
            value = values[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{key} must be a whole number of at least 1")
        if values["perfect_storm_min_mediums"] > len(PerfectStormRule.STORM_FACTORS):
            raise ValueError("perfect_storm_min_mediums cannot exceed the number of storm factors (3)")
        if values["delay_days_high"] < values["delay_days_limit"]:
            raise ValueError("delay_days_high must be at least delay_days_limit")

    @classmethod
    def from_dict(cls, data):
        """Rebuild a config from saved JSON data (keys not given keep their defaults)."""
        return cls(**dict(data))

    def to_dict(self):
        return dict(self._values)

    @property
    def confidence_min(self):
        return self._values["confidence_min"]

    @property
    def history_window_days(self):
        return self._values["history_window_days"]

    @property
    def perfect_storm_min_mediums(self):
        return self._values["perfect_storm_min_mediums"]

    @property
    def data_max_age_hours(self):
        return self._values["data_max_age_hours"]

    @property
    def delay_days_limit(self):
        return self._values["delay_days_limit"]

    @property
    def delay_days_high(self):
        return self._values["delay_days_high"]
