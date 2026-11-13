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
        new_departure: datetime,
        new_arrival: datetime,
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
    def new_departure(self) -> datetime:
        return self.__new_departure

    @property
    def new_arrival(self) -> datetime:
        return self.__new_arrival
    
    
    