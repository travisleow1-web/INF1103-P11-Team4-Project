"""Dev-only stand-ins for the AI and Logic managers, used by the tests and by the web app's demo mode.
They run only when DEMO_MODE=1 (see main.create_app), never in normal use."""
from datetime import datetime, timezone
from model.ai_assessment import AIAssessment
from model.ai_status import AIStatus
from model.decision import Decision
from model.outcome import Outcome
from model.risk_factor import RiskFactor
from model.risk_level import RiskLevel
from model.risk_type import RiskType

LEVELS = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
OUTCOMES = {RiskLevel.LOW: Outcome.PROCEED, RiskLevel.MEDIUM: Outcome.INSURE, RiskLevel.HIGH: Outcome.ESCALATE}


class FakeAI:
    """Gives SHP-001 a medium weather risk, SHP-002 high, SHP-003 low, and so on."""

    def assess(self, shipment):
        """Return a LIVE assessment whose severity depends only on the shipment number."""
        number = int(shipment.shipment_id.split("-")[1])
        level = LEVELS[number % 3]
        factor = RiskFactor(RiskType.WEATHER, level, shipment.origin.code, "open_meteo_weather",
                            f"Fake {level.label.lower()} weather")
        return AIAssessment([factor], [], RiskType.WEATHER, shipment.origin.code,
                            "None" if level == RiskLevel.LOW else "Delay", 0.8, False,
                            AIStatus.LIVE, datetime.now(timezone.utc))


class FakeLogic:
    """Copies the first risk factor's severity into the decision. High risk needs a human."""

    def evaluate(self, shipment, assessment, now):
        """Return a Decision with the risk and outcome taken from the fake assessment."""
        level = assessment.risk_factors[0].severity
        decision = Decision(shipment.shipment_id)
        decision.raise_risk(level)
        decision.set_outcome(OUTCOMES[level])
        decision.add_note(f"Fake rule: weather risk is {level.label}")
        if level == RiskLevel.HIGH:
            decision.require_human()
        return decision
