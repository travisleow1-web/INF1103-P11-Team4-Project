import time
from datetime import datetime, timedelta, timezone
from model.ai_assessment import AIAssessment
from model.ai_status import AIStatus
from model.decision import Decision
from model.fetch_event import FetchEvent
from model.fetch_stage import FetchStage
from model.outcome import Outcome
from model.risk_factor import RiskFactor
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from logic_layer.reschedule_rule import RescheduleRule
from logic_layer.rule_config import RuleConfig

LEVELS = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
OUTCOMES = {RiskLevel.LOW: Outcome.PROCEED, RiskLevel.MEDIUM: Outcome.INSURE, RiskLevel.HIGH: Outcome.ESCALATE}


class FakeAI:
    def __init__(self, delay: float = 0.0):
        self.__tried = set()
        self.__listeners = []
        self.__delay = delay

    def add_listener(self, listener):
        self.__listeners.append(listener)

    def remove_listener(self, listener):
        if listener in self.__listeners:
            self.__listeners.remove(listener)

    def __tell(self, shipment, stage, detail=None):
        event = FetchEvent(shipment.shipment_id, stage, detail=detail)
        for listener in tuple(self.__listeners):
            listener.on_event(event)

    def assess(self, shipment):
        number = int(shipment.shipment_id.split("-")[1])
        first_try = shipment.shipment_id not in self.__tried
        self.__tried.add(shipment.shipment_id)
        self.__tell(shipment, FetchStage.STARTED)
        if self.__delay:
            time.sleep(self.__delay)
        if number % 9 == 0 and first_try:
            self.__tell(shipment, FetchStage.FAILED, "the demo AI did not answer")
            return AIAssessment.fallback()
        self.__tell(shipment, FetchStage.SUCCEEDED)
        level = LEVELS[number % 3]
        factor = RiskFactor(RiskType.WEATHER, level, shipment.origin.code, "open_meteo_weather",
                            f"Fake {level.label.lower()} weather")
        clear = shipment.departure + timedelta(days=4) if level == RiskLevel.HIGH else None
        return AIAssessment([factor], [], RiskType.WEATHER, shipment.origin.code,
                            "None" if level == RiskLevel.LOW else "Delay", 0.8, False,
                            AIStatus.LIVE, datetime.now(timezone.utc), clear)


class FakeLogic:
    def evaluate(self, shipment, assessment, now):
        decision = Decision(shipment.shipment_id)
        if assessment.is_fallback():            # no AI answer: low risk, but a person must look
            decision.raise_risk(RiskLevel.LOW)
            decision.set_outcome(Outcome.ESCALATE)
            decision.add_note("Fake rule: the AI was unavailable")
            decision.require_human()
            return decision
        level = assessment.risk_factors[0].severity
        decision.raise_risk(level)
        decision.set_outcome(OUTCOMES[level])
        decision.add_note(f"Fake rule: weather risk is {level.label}")
        if level == RiskLevel.HIGH:
            decision.require_human()
        RescheduleRule().apply(shipment, assessment, decision, now)
        return decision

    def __init__(self):
        self.__config = RuleConfig()

    @property
    def config(self):
        return self.__config

    def configure(self, fields):
        self.__config = RuleConfig.from_text(fields)
        return self.__config
