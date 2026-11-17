from abc import ABC, abstractmethod
from datetime import datetime
from typing import List
from model.search_criteria import SearchCriteria
from model.shipment_record import ShipmentRecord


class DataManager(ABC):
    @abstractmethod
    def save(self, record: ShipmentRecord) -> None:
        ...

    @abstractmethod
    def replace(self, record: ShipmentRecord) -> None:
        ...

    @abstractmethod
    def find(self, criteria: SearchCriteria) -> List[ShipmentRecord]:
        ...

    @abstractmethod
    def find_route_history(self, route_id: str, since: datetime) -> List[ShipmentRecord]:
        ...
