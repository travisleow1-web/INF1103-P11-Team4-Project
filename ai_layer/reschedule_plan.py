from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from model import shipment
from model.ai_assessment import AIAssessment
from model.shipment import Shipment


class ReschedulePlan:
    """Represents a plan for rescheduling a shipment."""
    
    def __init__(
        self, 
        shipment: Shipment,
        new_departure: date,
        new_arrival: date,
        reason: str,
        assessment: AIAssessment,
    ):
        self.__shipment_id = shipment.shipment_id
        self.__original_departure = shipment.departure
        self.__original_arrival = shipment.arrival
        self.__new_departure = new_departure
        self.__new_arrival = new_arrival
        self.__reason = reason
        self.__assessment = assessment
        
    @property
    def new_departure(self) -> date:
        return self.__new_departure

    @property
    def new_arrival(self) -> date:
        return self.__new_arrival
    
    
class RescheduleManager:
    """Evaluates an AIAssessment and proposes a ReschedulePlan when a clearer departure window exists."""

    def evaluate(self, shipment: Shipment, assessment: AIAssessment) -> Optional[ReschedulePlan]:
        clear_date = assessment.earliest_clear_departure
        if clear_date is None or clear_date <= shipment.departure:
            return None

        has_severe_risk = any(r.severity in ("High", "Extreme") for r in assessment.risk_factors)
        if not has_severe_risk:
            return None

        transit_duration = shipment.arrival - shipment.departure
        new_departure = clear_date
        new_arrival = new_departure + transit_duration
        reason = f"{assessment.primary_risk_factor} at {assessment.affected_location}"

        return ReschedulePlan(
            shipment=shipment,
            new_departure= new_departure,
            new_arrival= new_arrival,
            reason= reason,
            assessment= assessment,
        )