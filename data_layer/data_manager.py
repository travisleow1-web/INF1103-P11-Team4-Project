from abc import ABC, abstractmethod
from datetime import datetime
from typing import List
from model.search_criteria import SearchCriteria
from model.shipment_record import ShipmentRecord


class DataManager(ABC):
    """What IO and main.py need from storage. Every backend raises StorageError, never its own errors."""

    @abstractmethod
    def save(self, record: ShipmentRecord) -> None:
        """Store one ShipmentRecord. shipment_id is the unique key: saving a second one is an error."""

    @abstractmethod
    def find(self, criteria: SearchCriteria) -> List[ShipmentRecord]:
        """Return the records that match a SearchCriteria, newest first. No filters returns everything."""

    @abstractmethod
    def find_route_history(self, route_id: str, since: datetime) -> List[ShipmentRecord]:
        """Return the records on a route ('SGSIN-NLRTM') saved at or after since, newest first.

        Records whose assessment is a FALLBACK are skipped: the AI never looked at them.
        """
