from datetime import datetime
from typing import List
from model.search_criteria import SearchCriteria
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError
from .data_manager import DataManager


class UnavailableDataManager(DataManager):
    """Stands in when the database could not be reached at startup. Every call raises StorageError.

    The app keeps running: IO shows the message, and assess_shipments reports each record as not saved.
    """

    def __init__(self, message: str):
        self.__message = message

    @property
    def message(self) -> str:
        """Why storage is unavailable, for the page banner."""
        return self.__message

    def save(self, record: ShipmentRecord) -> None:
        """Always fails: there is nowhere to save."""
        raise StorageError(self.__message)

    def find(self, criteria: SearchCriteria) -> List[ShipmentRecord]:
        """Always fails: there is nothing to search."""
        raise StorageError(self.__message)

    def find_route_history(self, route_id: str, since: datetime) -> List[ShipmentRecord]:
        """Always fails: there is no history to read."""
        raise StorageError(self.__message)
