"""Dev-only stand-ins for the AI and Logic managers, until the real classes exist.
They never run in the product. They only let the IO and Data layers be tried end to end."""
from model.ai_assessment import AIAssessment
from model.decision import Decision

LEVELS = ["LOW", "MEDIUM", "HIGH"]
OUTCOMES = {"LOW": "PROCEED", "MEDIUM": "INSURE", "HIGH": "ESCALATE"}


class FakeAI:
    def assess(self, shipment):
        number = int(shipment.shipment_id.split("-")[1])
        level = LEVELS[number % 3]
        return AIAssessment({
            "ai_status": "LIVE",
            "expected_impact": "minor_delay" if level == "LOW" else "major_delay",
            "confidence_score": 0.8,
            "primary_risk_factor": "WEATHER",
            "conflicting_sources": False,
            "risk_factors": [{"type": "WEATHER", "severity": level}],
        })


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
