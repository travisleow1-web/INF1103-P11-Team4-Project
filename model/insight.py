from dataclasses import dataclass
from .risk_level import RiskLevel
from .risk_type import RiskType


@dataclass(frozen=True)
class Insight:
    code: str
    risk_type: RiskType
    severity: RiskLevel
    location: str
    estimated_delay_days: int

    def to_dict(self) -> dict:
        return {"code": self.code, "risk_type": self.risk_type.value, "severity": self.severity.name,
                "location": self.location, "estimated_delay_days": self.estimated_delay_days}

    @classmethod
    def from_dict(cls, data: dict) -> "Insight":
        return cls(str(data["code"]), RiskType(data["risk_type"]), RiskLevel.parse(data["severity"]),
                   str(data["location"]), int(data["estimated_delay_days"]))
