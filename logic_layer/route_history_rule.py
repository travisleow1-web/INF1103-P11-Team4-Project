from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from data_layer.data_manager import DataManager
from model.ai_assessment import AIAssessment
from model.decision import Decision
from model.flag import Flag
from model.risk_level import RiskLevel
from model.shipment import Shipment
from model.storage_error import StorageError
from .business_rule import BusinessRule

if TYPE_CHECKING:
    from .rule_config import RuleConfig


class RouteHistoryRule(BusinessRule):
    def __init__(self, config: "RuleConfig", data: DataManager):
        self.__config = config
        self.__data = data

    def apply(self, shipment: Shipment, assessment: AIAssessment, decision: Decision, now: datetime) -> None:
        if decision.risk_level != RiskLevel.LOW or assessment.is_fallback():
            return
        window = self.__config.history_window_days
        route_id = shipment.route_id()
        try:
            past = self.__data.find_route_history(route_id, now - timedelta(days=window))
        except StorageError as error:
            decision.add_note(f"Rule 3: could not read route history ({error}), needs human",
                              Flag.ROUTE_HISTORY_UNAVAILABLE, human=True)
            return
        problems = [r for r in past if r.decision.risk_level > RiskLevel.LOW or r.is_delayed()]
        if not problems:
            decision.add_note(f"Rule 3: no flagged or delayed shipments on this route in the last {window} days")
            return
        decision.hold()
        decision.add_note(f"Rule 3: AI says Low but {len(problems)} shipment(s) on route {route_id} "
                          f"were flagged or delayed in the last {window} days", Flag.CAUTIONARY_OVERRIDE,
                          "Require human dispatcher sign-off", human=True)
