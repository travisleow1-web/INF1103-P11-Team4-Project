from datetime import datetime, timezone


class ShipmentRecord:
    """Placeholder shared-model class: one assessed shipment, as saved."""

    def __init__(self, shipment, assessment, decision, saved_at=None):
        self.__shipment = shipment
        self.__assessment = assessment
        self.__decision = decision
        self.__saved_at = saved_at or datetime.now(timezone.utc)

    @property
    def shipment(self):
        return self.__shipment

    @property
    def assessment(self):
        return self.__assessment

    @property
    def decision(self):
        return self.__decision

    @property
    def saved_at(self):
        return self.__saved_at
