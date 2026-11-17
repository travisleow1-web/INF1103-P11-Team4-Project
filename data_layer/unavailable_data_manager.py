from datetime import datetime
from typing import List
from model.search_criteria import SearchCriteria
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError
from .data_manager import DataManager


class UnavailableDataManager(DataManager):
    def __init__(self, message: str):
        self.__message = message

    @property
    def message(self) -> str:
        return self.__message

    def save(self, record: ShipmentRecord) -> None:
        raise StorageError(self.__message)

    def replace(self, record: ShipmentRecord) -> None:
        raise StorageError(self.__message)

    def find(self, criteria: SearchCriteria) -> List[ShipmentRecord]:
        raise StorageError(self.__message)

    def find_route_history(self, route_id: str, since: datetime) -> List[ShipmentRecord]:
        raise StorageError(self.__message)
