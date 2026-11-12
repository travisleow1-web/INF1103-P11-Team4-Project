import logging
from datetime import datetime
from typing import Optional
from data_layer.data_manager import DataManager
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.port_registry import PortRegistry
from model.shipment import Shipment
from .ai_insight_rule import AIInsightRule
from .data_quality_rule import DataQualityRule
from .insurance_rule import InsuranceRule
from .outcome_resolver import OutcomeResolver
from .perfect_storm_rule import PerfectStormRule
from .procurement_rule import ProcurementRule
from .route_history_rule import RouteHistoryRule
from .rule_config import RuleConfig
from .unregistered_location_rule import UnregisteredLocationRule

logger = logging.getLogger(__name__)


class LogicManager:
    """Turns one shipment's AI assessment into a Decision by running every business rule, then the resolver.

    Based on Jun Jie's LogicManager (Logic_ManagerPart2). Each rule runs on its own: a rule that fails
    leaves a "Rule error" note for a human instead of stopping the shipment.
    """

    def __init__(self, data: DataManager, ports: PortRegistry, config: Optional[RuleConfig] = None):
        self.__data = data      # association: used for route history, not owned
        self.__ports = ports
        self.__resolver = OutcomeResolver()
        self.__build(config or RuleConfig())

    def __build(self, config: RuleConfig) -> None:
        # Composition: the rules are created here and live only inside this LogicManager.
        self.__config = config
        self.__rules = (
            DataQualityRule(config),
            PerfectStormRule(config),
            AIInsightRule(config),
            InsuranceRule(),
            UnregisteredLocationRule(self.__ports),
            RouteHistoryRule(config, self.__data),  # after the risk-raising rules
            ProcurementRule(),
        )

    @property
    def config(self) -> RuleConfig:
        return self.__config

    @property
    def rules(self) -> tuple:
        return self.__rules

    def update_config(self, config: RuleConfig) -> None:
        """Apply new user-chosen thresholds (new feature); rebuilds the rules with them."""
        if not isinstance(config, RuleConfig):
            raise TypeError("config must be a RuleConfig")
        self.__build(config)

    def evaluate(self, shipment: Shipment, assessment: AIAssessment, now: datetime) -> Decision:
        """Run every rule on the shipment, then pick the outcome. now must be timezone-aware."""
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        decision = Decision(shipment.shipment_id)
        for rule in self.__rules:  # polymorphism: the same call for every rule type
            try:
                rule.apply(shipment, assessment, decision, now)
            except Exception as error:  # one broken rule must not stop the others
                logger.exception("%s failed on %s", rule.name, shipment.shipment_id)
                decision.add_note(f"{rule.name} could not run ({error}), needs human", Flag.RULE_ERROR, human=True)
        self.__resolver.resolve(decision)
        return decision
