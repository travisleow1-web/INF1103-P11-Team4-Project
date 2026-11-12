from dataclasses import dataclass
from .risk_level import RiskLevel
from .risk_type import RiskType


@dataclass(frozen=True)
class RiskFactor:
    """One risk the AI found on a route, with where it is and which feed reported it."""

    type: RiskType
    severity: RiskLevel
    location: str
    source: str
    detail: str

    def to_dict(self) -> dict:
        """Plain dict for saving: the type's value and the severity's NAME."""
        return {"type": self.type.value, "severity": self.severity.name, "location": self.location,
                "source": self.source, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: dict) -> "RiskFactor":
        """Rebuild from to_dict() output. Unknown types or severities raise ValueError."""
        return cls(RiskType(data["type"]), RiskLevel.parse(data["severity"]), str(data["location"]),
                   str(data["source"]), str(data["detail"]))
