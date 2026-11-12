from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.shipment import Shipment
from .business_rule import BusinessRule

if TYPE_CHECKING:
    from .rule_config import RuleConfig


class DataQualityRule(BusinessRule):
    """Sends a shipment to a human when the AI did not run or its answer cannot be trusted.

    Takes over the soft checks of Jun Jie's RecordValidator (Logic_ManagerPart2): low confidence,
    outdated external data and conflicting sources, plus the FALLBACK status.
    """

    def __init__(self, config: "RuleConfig"):
        self.__config = config

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        """Add a human-review note for each data-quality problem."""
        if assessment.is_fallback():
            decision.add_note("Data quality: the AI could not assess this shipment", Flag.AI_UNAVAILABLE, human=True)
            return
        config = self.__config
        if assessment.confidence_score < config.confidence_min:
            decision.add_note(f"Data quality: confidence {assessment.confidence_score:.2f} is below "
                              f"{config.confidence_min:.2f}", Flag.LOW_CONFIDENCE, human=True)
        if now - assessment.fetched_at > timedelta(hours=config.data_max_age_hours):
            decision.add_note(f"Data quality: external data is older than {config.data_max_age_hours}h",
                              Flag.OUTDATED_DATA, human=True)
        if assessment.conflicting_sources:
            decision.add_note("Data quality: the AI reported conflicting or missing information",
                              Flag.CONFLICTING_SOURCES, human=True)
