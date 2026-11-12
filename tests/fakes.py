"""Dev-only stand-ins for the AI and Logic managers, until the real classes exist.
They never run in the product. They only let the IO and Data layers be tried end to end."""
from datetime import datetime, timezone
from model.ai_assessment import AIAssessment
from model.ai_status import AIStatus
from model.decision import Decision
from model.risk_factor import RiskFactor
from model.risk_level import RiskLevel
from model.risk_type import RiskType

LEVELS = ["LOW", "MEDIUM", "HIGH"]
OUTCOMES = {"LOW": "PROCEED", "MEDIUM": "INSURE", "HIGH": "ESCALATE"}


class FakeAI:
    """Gives SHP-001 a medium weather risk, SHP-002 high, SHP-003 low, and so on."""

    def assess(self, shipment):
        """Return a LIVE assessment whose severity depends only on the shipment number."""
        number = int(shipment.shipment_id.split("-")[1])
        level = RiskLevel.parse(LEVELS[number % 3])
        factor = RiskFactor(RiskType.WEATHER, level, shipment.origin.code, "open_meteo_weather",
                            f"Fake {level.label.lower()} weather")
        return AIAssessment([factor], [], RiskType.WEATHER, shipment.origin.code,
                            "None" if level == RiskLevel.LOW else "Delay", 0.8, False,
                            AIStatus.LIVE, datetime.now(timezone.utc))


class FakeLogic:
    def evaluate(self, shipment, assessment, now):
        level = assessment.to_dict()["risk_factors"][0]["severity"]
        return Decision({
            "shipment_id": shipment.shipment_id,
            "overall_risk": level,
            "outcome": OUTCOMES[level],
            "needs_human": level == "HIGH",
            "hold_shipment": False,
            "flags": [], "actions": [], "alerts": [], "rationale": [],
        })
