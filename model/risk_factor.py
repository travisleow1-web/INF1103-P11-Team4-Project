from dataclasses import dataclass
from .risk_level import RiskLevel
from .risk_type import RiskType


@dataclass(frozen=True)
class RiskFactor:
    type: RiskType
    severity: RiskLevel
    location: str
    source: str
    detail: str

    def to_dict(self) -> dict:
        return {"type": self.type.value, "severity": self.severity.name, "location": self.location,
                "source": self.source, "detail": self.detail}

    @classmethod
    def from_dict(cls, data: dict) -> "RiskFactor":
        return cls(RiskType(data["type"]), RiskLevel.parse(data["severity"]), str(data["location"]),
                   str(data["source"]), str(data["detail"]))
