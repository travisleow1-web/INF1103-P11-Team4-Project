from enum import IntEnum


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    EXTREME = 4

    @property
    def label(self) -> str:
        return self.name.capitalize()

    @classmethod
    def parse(cls, text: str) -> "RiskLevel":
        if isinstance(text, cls):
            return text
        key = str(text).strip().upper()
        if key not in cls.__members__:
            raise ValueError(f"Unknown risk level {text!r}")
        return cls[key]
