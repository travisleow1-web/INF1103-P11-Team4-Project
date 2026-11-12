from abc import ABC, abstractmethod
from datetime import datetime


class DataManager(ABC):
    """What IO and main.py need from storage. Every backend raises StorageError, never its own errors."""

    @abstractmethod
    def save(self, record):
        """Store one ShipmentRecord. shipment_id is the unique key: saving a second one is an error."""

    @abstractmethod
    def find(self, criteria):
        """Return the records that match a SearchCriteria, newest first. No filters returns everything."""

    @abstractmethod
    def find_route_history(self, route_id: str, since: datetime) -> list:
        """Return the records on a route ('SGSIN-NLRTM') saved at or after since, newest first.

        Records whose assessment is a FALLBACK are skipped: the AI never looked at them.
        """
