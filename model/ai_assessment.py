from datetime import date, datetime, timezone
from typing import Iterable, Optional
from .ai_status import AIStatus
from .insight import Insight
from .risk_factor import RiskFactor
from .risk_type import RiskType


class AIAssessment:
    """What the AI found for one shipment. It holds facts only; the Logic manager decides what to do."""

    def __init__(self, risk_factors: Iterable[RiskFactor], insights: Iterable[Insight],
                 primary_risk_factor: RiskType, affected_location: str, expected_impact: str,
                 confidence_score: float, conflicting_sources: bool, status: AIStatus,
                 fetched_at: datetime, earliest_clear_departure: Optional[date] = None):
        if fetched_at.tzinfo is None:
            raise ValueError("fetched_at must be timezone-aware")
        self.__risk_factors = tuple(risk_factors)
        self.__insights = tuple(insights)
        self.__primary_risk_factor = RiskType(primary_risk_factor)
        self.__affected_location = affected_location
        self.__expected_impact = expected_impact
        self.__confidence_score = float(confidence_score)
        self.__conflicting_sources = bool(conflicting_sources)
        self.__status = AIStatus(status)
        self.__fetched_at = fetched_at
        self.__earliest_clear_departure = earliest_clear_departure

    @classmethod
    def fallback(cls, now: Optional[datetime] = None) -> "AIAssessment":
        """The empty assessment used when the AI could not run. It is never cached."""
        return cls([], [], RiskType.NONE, "Unknown", "None", 0.0, False, AIStatus.FALLBACK,
                   now or datetime.now(timezone.utc))

    @property
    def risk_factors(self) -> tuple:
        return self.__risk_factors

    @property
    def insights(self) -> tuple:
        return self.__insights

    @property
    def primary_risk_factor(self) -> RiskType:
        return self.__primary_risk_factor

    @property
    def affected_location(self) -> str:
        return self.__affected_location

    @property
    def expected_impact(self) -> str:
        return self.__expected_impact

    @property
    def confidence_score(self) -> float:
        return self.__confidence_score

    @property
    def conflicting_sources(self) -> bool:
        return self.__conflicting_sources

    @property
    def status(self) -> AIStatus:
        return self.__status

    @property
    def fetched_at(self) -> datetime:
        return self.__fetched_at
    
    @property
    def earliest_clear_departure(self) -> Optional[date]:
        return self.__earliest_clear_departure

    def is_fallback(self) -> bool:
        """True when the AI did not run for this shipment."""
        return self.__status is AIStatus.FALLBACK

    def to_dict(self) -> dict:
        """Plain dict for saving and display. Enums become their values, the time ISO text."""
        return {
            "risk_factors": [f.to_dict() for f in self.__risk_factors],
            "insights": [i.to_dict() for i in self.__insights],
            "primary_risk_factor": self.__primary_risk_factor.value,
            "affected_location": self.__affected_location,
            "expected_impact": self.__expected_impact,
            "confidence_score": self.__confidence_score,
            "conflicting_sources": self.__conflicting_sources,
            "ai_status": self.__status.value,
            "fetched_at": self.__fetched_at.isoformat(),
            "earliest_clear_departure": (
                self.__earliest_clear_departure.isoformat()
                if self.__earliest_clear_departure else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AIAssessment":
        """Rebuild from to_dict() output. A missing key is a KeyError, a bad value a ValueError."""
        text = str(data["fetched_at"])
        if text.endswith("Z"):                     # Python 3.10 fromisoformat does not read "Z"
            text = text[:-1] + "+00:00"
        fetched_at = datetime.fromisoformat(text)
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            
        raw_clear = data.get("earliest_clear_departure")
        earliest_clear = date.fromisoformat(str(raw_clear)) if raw_clear else None
        
        return cls(
            [RiskFactor.from_dict(f) for f in data["risk_factors"]],
            [Insight.from_dict(i) for i in data["insights"]],
            RiskType(data["primary_risk_factor"]),
            str(data["affected_location"]),
            str(data["expected_impact"]),
            data["confidence_score"],
            data["conflicting_sources"],
            AIStatus(data["ai_status"]),
            fetched_at,
            earliest_clear, 
        )
