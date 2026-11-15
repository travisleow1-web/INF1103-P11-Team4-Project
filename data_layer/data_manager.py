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
        """Records matching criteria, newest first (no filters: everything). Damaged records are skipped and logged;
        StorageError means the store itself could not be read."""

    @abstractmethod
    def find_route_history(self, route_id: str, since: datetime) -> List[ShipmentRecord]:
        """Records on a route ('SGSIN-NLRTM') saved at or after since (timezone-aware, else ValueError), newest
        first. FALLBACK assessments are skipped: the AI never looked at them."""
