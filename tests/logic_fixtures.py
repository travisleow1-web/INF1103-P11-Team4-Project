"""Small typed stand-ins shared by the Logic tests. No network, no AI, no database."""
from datetime import date, datetime, timezone
from model.ai_assessment import AIAssessment
from model.ai_status import AIStatus
from model.decision import Decision
from model.insight import Insight
from model.port import Port
from model.port_registry import PortRegistry
from model.risk_factor import RiskFactor
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from model.shipment import Shipment
from model.storage_error import StorageError

SINGAPORE = Port("SGSIN", "Singapore", "SG", 1.26, 103.84)
ROTTERDAM = Port("NLRTM", "Rotterdam", "NL", 51.9, 4.5)
PORTS = PortRegistry([SINGAPORE, ROTTERDAM])

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)


def shipment(shipment_id="SHP-001"):
    """SGSIN to NLRTM, 01/12/2026 to 28/12/2026."""
    return Shipment(shipment_id, SINGAPORE, ROTTERDAM, date(2026, 12, 1), date(2026, 12, 28))


def factor(risk_type=RiskType.WEATHER, severity=RiskLevel.MEDIUM, location="SGSIN"):
    return RiskFactor(risk_type, severity, location, "open_meteo_weather", "test factor")


def insight(code="POTENTIAL_DELAY", severity=RiskLevel.MEDIUM, days=0, location="SGSIN",
            risk_type=RiskType.WEATHER):
    return Insight(code, risk_type, severity, location, days)


def assessment(factors=(), insights=(), primary=RiskType.NONE, location="SGSIN", impact="None",
               confidence=0.9, conflicting=False, status=AIStatus.LIVE, fetched_at=NOW):
    """A real AIAssessment. By default it is clean: no factors, high confidence, fresh data."""
    return AIAssessment(factors, insights, primary, location, impact, confidence, conflicting, status, fetched_at)


def decision(shipment_id="SHP-001"):
    return Decision(shipment_id)


class FakeHistory:
    """A data manager stand-in for route history: returns fixed records or raises the error it was given."""

    def __init__(self, records=(), error=None):
        self.records = list(records)
        self.error = error
        self.calls = []

    def find_route_history(self, route_id, since):
        self.calls.append((route_id, since))
        if self.error:
            raise self.error
        return self.records


def broken_history(message="database down"):
    return FakeHistory(error=StorageError(message))
