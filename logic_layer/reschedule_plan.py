from datetime import date
from model.ai_assessment import AIAssessment


class ReschedulePlan:
    """A suggested later departure for one shipment, with the same journey length."""

    def __init__(self, shipment_id: str, original_departure: date, original_arrival: date,
                 new_departure: date, new_arrival: date, reason: str, assessment: AIAssessment):
        self.__shipment_id = shipment_id
        self.__original_departure = original_departure
        self.__original_arrival = original_arrival
        self.__new_departure = new_departure
        self.__new_arrival = new_arrival
        self.__reason = reason
        self.__assessment = assessment

    @property
    def shipment_id(self) -> str:
        return self.__shipment_id

    @property
    def original_departure(self) -> date:
        return self.__original_departure

    @property
    def original_arrival(self) -> date:
        return self.__original_arrival

    @property
    def new_departure(self) -> date:
        return self.__new_departure

    @property
    def new_arrival(self) -> date:
        return self.__new_arrival

    @property
    def reason(self) -> str:
        return self.__reason

    @property
    def assessment(self) -> AIAssessment:
        return self.__assessment
