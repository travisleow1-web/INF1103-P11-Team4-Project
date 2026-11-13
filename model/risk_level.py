from enum import IntEnum


class RiskLevel(IntEnum):
    """Ordered risk levels, so rules can compare them (LOW < MEDIUM < HIGH < EXTREME).

    Based on Jun Jie's RiskLevel (Logic_ManagerPart2), with EXTREME added and strict parsing.
    """

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    EXTREME = 4

    @property
    def label(self) -> str:
        """Display form: 'Low', 'Medium', 'High' or 'Extreme'."""
        return self.name.capitalize()

    @classmethod
    def parse(cls, text: str) -> "RiskLevel":
        """Read a name or label in any case ('HIGH', 'High', 'high'). Anything else is a ValueError."""
        if isinstance(text, cls):
            return text
        key = str(text).strip().upper()
        if key not in cls.__members__:
            raise ValueError(f"Unknown risk level {text!r}")
        return cls[key]
