from collections.abc import Mapping
from .perfect_storm_rule import PerfectStormRule


class RuleConfig:
    """Every business-rule threshold in one validated object (new feature: user-configurable rules).

    Based on Jun Jie's RuleConfig (Logic_ManagerPart2).
    """

    __DEFAULTS = {
        "confidence_min": 0.60,           # below this, AI output needs a human
        "history_window_days": 21,        # Rule 3 look-back
        "perfect_storm_min_mediums": 3,   # Rule 1
        "data_max_age_hours": 24,         # external data older than this is "outdated"
        "delay_days_limit": 3,            # Rule 1b: delay that raises risk to Medium
        "delay_days_high": 7,             # Rule 1b: delay that raises risk to High
    }
    __WHOLE_NUMBER_KEYS = ("history_window_days", "perfect_storm_min_mediums",
                         "data_max_age_hours", "delay_days_limit", "delay_days_high")

    def __init__(self, **overrides: float):
        """Start from the defaults and apply the given settings. Unknown or bad settings raise ValueError."""
        unknown = set(overrides) - set(self.__DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown rule setting(s): {sorted(unknown)}")
        values = {**self.__DEFAULTS, **overrides}
        self.__validate(values)
        self.__values = values

    def __validate(self, values: dict) -> None:
        conf = values["confidence_min"]
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0.0 <= conf <= 1.0:
            raise ValueError("confidence_min must be a number between 0 and 1")
        for key in self.__WHOLE_NUMBER_KEYS:
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
        """Rebuild a config from saved data. Keys not given keep their defaults.

        Anything that is not a mapping, an unknown key or a bad value raises ValueError.
        """
        if not isinstance(data, Mapping):
            raise ValueError("Rule settings must be a mapping of setting names to values")
        return cls(**{str(key): value for key, value in data.items()})
        
    @classmethod
    def from_text(cls, fields: Mapping[str, str]) -> "RuleConfig":
        """Build a config from form text. Blank boxes keep their defaults; bad text raises ValueError."""
        values = {}
        for key, text in fields.items():
            text = str(text).strip()
            if not text:
                continue
            try:
                values[key] = int(text) if key in cls.__WHOLE_NUMBER_KEYS else float(text)
            except ValueError:
                raise ValueError(f"{key} must be a number, not {text!r}") from None
        return cls(**values)


    def to_dict(self) -> dict:
        """The thresholds as a plain dict (a copy)."""
        return dict(self.__values)

    @property
    def confidence_min(self) -> float:
        """AI confidence below this needs a human."""
        return self.__values["confidence_min"]

    @property
    def history_window_days(self) -> int:
        """How many days of route history Rule 3 looks back."""
        return self.__values["history_window_days"]

    @property
    def perfect_storm_min_mediums(self) -> int:
        """How many storm factors at Medium or above make a Perfect Storm."""
        return self.__values["perfect_storm_min_mediums"]

    @property
    def data_max_age_hours(self) -> int:
        """External data older than this many hours is outdated."""
        return self.__values["data_max_age_hours"]

    @property
    def delay_days_limit(self) -> int:
        """A predicted delay of at least this many days raises the risk to Medium."""
        return self.__values["delay_days_limit"]

    @property
    def delay_days_high(self) -> int:
        """A predicted delay of at least this many days raises the risk to High."""
        return self.__values["delay_days_high"]
