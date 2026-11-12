from .perfect_storm_rule import PerfectStormRule


class RuleConfig:
    """Every business-rule threshold in one validated object (new feature: user-configurable rules).

    Based on Jun Jie's RuleConfig (Logic_ManagerPart2).
    """

    DEFAULTS = {
        "confidence_min": 0.60,           # below this, AI output needs a human
        "history_window_days": 21,        # Rule 3 look-back
        "perfect_storm_min_mediums": 3,   # Rule 1
        "data_max_age_hours": 24,         # external data older than this is "outdated"
        "delay_days_limit": 3,            # Rule 1b: delay that raises risk to Medium
        "delay_days_high": 7,             # Rule 1b: delay that raises risk to High
    }
    WHOLE_NUMBER_KEYS = ("history_window_days", "perfect_storm_min_mediums",
                         "data_max_age_hours", "delay_days_limit", "delay_days_high")

    def __init__(self, **overrides):
        unknown = set(overrides) - set(self.DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown rule setting(s): {sorted(unknown)}")
        values = {**self.DEFAULTS, **overrides}
        self.__validate(values)
        self.__values = values

    def __validate(self, values: dict) -> None:
        conf = values["confidence_min"]
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
            raise ValueError("confidence_min must be a number between 0 and 1")
        for key in self.WHOLE_NUMBER_KEYS:
            value = values[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{key} must be a whole number of at least 1")
        storm_count = len(PerfectStormRule.STORM_FACTORS)
        if values["perfect_storm_min_mediums"] > storm_count:
            raise ValueError(f"perfect_storm_min_mediums cannot exceed the number of storm factors ({storm_count})")
        if values["delay_days_high"] < values["delay_days_limit"]:
            raise ValueError("delay_days_high must be at least delay_days_limit")

    @classmethod
    def from_dict(cls, data: dict) -> "RuleConfig":
        """Rebuild a config from saved data. Keys not given keep their defaults; bad values raise ValueError."""
        return cls(**dict(data))

    def to_dict(self) -> dict:
        """The thresholds as a plain dict (a copy)."""
        return dict(self.__values)

    @property
    def confidence_min(self) -> float:
        return self.__values["confidence_min"]

    @property
    def history_window_days(self) -> int:
        return self.__values["history_window_days"]

    @property
    def perfect_storm_min_mediums(self) -> int:
        return self.__values["perfect_storm_min_mediums"]

    @property
    def data_max_age_hours(self) -> int:
        return self.__values["data_max_age_hours"]

    @property
    def delay_days_limit(self) -> int:
        return self.__values["delay_days_limit"]

    @property
    def delay_days_high(self) -> int:
        return self.__values["delay_days_high"]
