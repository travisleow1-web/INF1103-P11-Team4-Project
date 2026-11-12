"""Small stand-ins shared by the IO tests. No network, no AI, no database."""
from datetime import date, datetime, timezone
from io_layer.io_manager import IOManager
from io_layer.shipment_validator import ShipmentValidator
from model.ai_assessment import AIAssessment
from model.ai_status import AIStatus
from model.decision import Decision
from model.outcome import Outcome
from model.port import Port
from model.port_registry import PortRegistry
from model.risk_factor import RiskFactor
from model.risk_level import RiskLevel
from model.risk_type import RiskType
from model.shipment import Shipment
from model.shipment_record import ShipmentRecord

SINGAPORE = Port("SGSIN", "Singapore", "SG", 1.26, 103.84)
ROTTERDAM = Port("NLRTM", "Rotterdam", "NL", 51.9, 4.5)
PORTS = PortRegistry([SINGAPORE, ROTTERDAM])

FETCHED_AT = datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)


def live_assessment(status=AIStatus.LIVE):
    """A real AIAssessment: low piracy risk and a medium weather risk at Singapore."""
    factors = [RiskFactor(RiskType.PIRACY_THREAT, RiskLevel.LOW, "SGSIN", "gdelt_news", "Patrols active"),
               RiskFactor(RiskType.WEATHER, RiskLevel.MEDIUM, "SGSIN", "open_meteo_weather", "Heavy rain")]
    return AIAssessment(factors, [], RiskType.WEATHER, "SGSIN", "Delay", 0.8, False, status, FETCHED_AT)


def row(**changes):
    """A valid raw shipment row, with any fields overridden."""
    base = {"origin_port": "SGSIN", "destination_port": "NLRTM",
            "departure_time": "01/12/2026", "arrival_time": "20/12/2026"}
    return {**base, **changes}


class FakeData:
    """Returns fixed records, remembers the last criteria, or raises the error it was given."""

    def __init__(self, records=None, error=None):
        self.records = records or []
        self.error = error
        self.last_criteria = None

    def find(self, criteria):
        self.last_criteria = criteria
        if self.error:
            raise self.error
        return self.records


def make_io(data=None):
    return IOManager(ShipmentValidator(PORTS), data or FakeData(), PORTS)


def record(shipment_id="SHP-001", fallback=False):
    """A saved record for the IO tests: SGSIN to NLRTM, 01/12/2026 to 20/12/2026, low risk."""
    return saved_record(shipment_id, arrival=date(2026, 12, 20), fallback=fallback)


def saved_record(shipment_id="SHP-001", risk="LOW", outcome="PROCEED", needs_human=False,
                 departure=date(2026, 12, 1), arrival=date(2026, 12, 28), fallback=False, saved_at=None,
                 origin=SINGAPORE, destination=ROTTERDAM):
    """A real ShipmentRecord of the kind the Data manager stores."""
    shipment = Shipment(shipment_id, origin, destination, departure, arrival)
    assessment = AIAssessment.fallback(FETCHED_AT) if fallback else live_assessment()
    decision = Decision(shipment_id)
    decision.raise_risk(RiskLevel.parse(risk))
    decision.set_outcome(Outcome(outcome))
    if needs_human:
        decision.require_human()
    return ShipmentRecord(shipment, assessment, decision,
                          saved_at or datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc))
