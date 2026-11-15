"""Dev-only stand-ins for the AI and Logic managers, used by the tests and by the web app's demo mode.
They run only when DEMO_MODE=1 (see main.create_app), never in normal use."""
from datetime import datetime, timedelta, timezone
from model.ai_assessment import AIAssessment
from model.ai_status import AIStatus
from model.decision import Decision
from model.outcome import Outcome
from model.risk_factor import RiskFactor
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from logic_layer.reschedule_rule import RescheduleRule
from logic_layer.rule_config import RuleConfig

LEVELS = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
OUTCOMES = {RiskLevel.LOW: Outcome.PROCEED, RiskLevel.MEDIUM: Outcome.INSURE, RiskLevel.HIGH: Outcome.ESCALATE}


class FakeAI:
    """Gives SHP-001 a medium weather risk, SHP-002 high, SHP-003 low, and so on.

    A high risk also gets a clear departure date 4 days after the planned one, as if the forecast scan
    had found the weather clearing then. That is what lets the demo show the reschedule suggestion.
    """

    def assess(self, shipment):
        """Return a LIVE assessment whose severity depends only on the shipment number."""
        number = int(shipment.shipment_id.split("-")[1])
        level = LEVELS[number % 3]
        factor = RiskFactor(RiskType.WEATHER, level, shipment.origin.code, "open_meteo_weather",
                            f"Fake {level.label.lower()} weather")
        clear = shipment.departure + timedelta(days=4) if level == RiskLevel.HIGH else None
        return AIAssessment([factor], [], RiskType.WEATHER, shipment.origin.code,
                            "None" if level == RiskLevel.LOW else "Delay", 0.8, False,
                            AIStatus.LIVE, datetime.now(timezone.utc), clear)


class FakeLogic:
    """Copies the first risk factor's severity into the decision. High risk needs a human.

    It also runs the real RescheduleRule, so the demo shows the real reschedule suggestion.
    """

    def evaluate(self, shipment, assessment, now):
        """Return a Decision with the risk and outcome taken from the fake assessment."""
        level = assessment.risk_factors[0].severity
        decision = Decision(shipment.shipment_id)
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
        """The thresholds (shown on the rules page; the fake rule ignores them)."""
        return self.__config

    def configure(self, fields):
        """Accept typed thresholds like the real LogicManager."""
        self.__config = RuleConfig.from_text(fields)
        return self.__config
