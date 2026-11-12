from datetime import datetime
from typing import Any, Dict, Iterable
from model.ai_assessment import AIAssessment
from model.ai_status import AIStatus
from model.insight import Insight
from model.risk_factor import RiskFactor
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from .invalid_response_error import InvalidResponseError


class ResponseParser:
    """Turns the model's JSON reply into an AIAssessment, or rejects the whole reply.

    Closed values (risk type, severity, impact, source, insight code) must be in their list;
    locations are open text. Any invalid value raises InvalidResponseError.
    """

    def __init__(self, allowed_lists: Dict[str, Iterable[str]]):
        self.__lists = {kind: tuple(values) for kind, values in allowed_lists.items()}

    def parse(self, raw: Dict[str, Any], status: AIStatus, fetched_at: datetime) -> AIAssessment:
        """Build an AIAssessment with the given status and fetch time (a cached reply keeps its own)."""
        try:
            score = raw["confidence_score"]
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise ValueError("confidence_score must be a number")
            if not 0.0 <= score <= 1.0:
                raise ValueError("confidence_score must be between 0 and 1")
            if not isinstance(raw["conflicting_sources"], bool):    # bool("false") would be True
                raise ValueError("conflicting_sources must be true or false")
            return AIAssessment(
                [self.__factor(f) for f in raw["risk_factors"]],
                [self.__insight(i) for i in raw["insights"]],
                RiskType(raw["primary_risk_factor"]),
                self.__text(raw["affected_location"], "affected_location"),
                self.__check("impact", raw["expected_impact"]),
                score, raw["conflicting_sources"], status, fetched_at,
            )
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as error:
            raise InvalidResponseError(f"invalid AI response: {error}") from error

    def __factor(self, data: Dict[str, Any]) -> RiskFactor:
        risk_type = RiskType(data["type"])
        if risk_type is RiskType.NONE:
            raise ValueError("a risk factor cannot have type 'none'")
        return RiskFactor(risk_type, RiskLevel.parse(data["severity"]), self.__text(data["location"], "location"),
                          self.__check("source", data["source"]), self.__text(data["detail"], "detail"))

    def __insight(self, data: Dict[str, Any]) -> Insight:
        days = data["estimated_delay_days"]
        if isinstance(days, bool) or not isinstance(days, int) or days < 0:
            raise ValueError("estimated_delay_days must be a whole number of days, 0 or more")
        return Insight(self.__check("insight_code", data["code"]), RiskType(data["risk_type"]),
                       RiskLevel.parse(data["severity"]), self.__text(data["location"], "location"), days)

    @staticmethod
    def __text(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{field} must be text")
        return value

    def __check(self, kind: str, value: Any) -> str:
        if value not in self.__lists[kind]:
            raise ValueError(f"{kind} {value!r} is not allowed")
        return value
