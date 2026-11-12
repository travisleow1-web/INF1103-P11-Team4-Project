from abc import ABC, abstractmethod


class DataManager(ABC):
    """What IO and main.py need from storage. Every backend raises StorageError, never its own errors."""

    @abstractmethod
    def save(self, record):
        """Store one ShipmentRecord. shipment_id is the unique key: saving a second one is an error."""

    @abstractmethod
    def find(self, criteria):
        """Return the records that match a SearchCriteria, newest first. No filters returns everything."""
