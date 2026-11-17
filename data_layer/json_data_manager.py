import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Union
from model.port_registry import PortRegistry
from model.search_criteria import SearchCriteria
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError
from .data_manager import DataManager
from .record_serializer import RecordSerializer


class JsonDataManager(DataManager):
    def __init__(self, path: Union[str, Path], ports: PortRegistry):
        self.__path = Path(path)
        self.__serializer = RecordSerializer(ports)
        self.__lock = threading.Lock()

    def save(self, record: ShipmentRecord) -> None:
        shipment_id = record.shipment.shipment_id
        with self.__lock:                      # read, check and write as one step
            documents = self.__load()
            if any(d.get("shipment_id") == shipment_id for d in documents):
                raise StorageError(f"{shipment_id} is already saved")
            documents.append(self.__serializer.to_document(record))
            self.__write(documents)

    def replace(self, record: ShipmentRecord) -> None:
        shipment_id = record.shipment.shipment_id
        with self.__lock:                      # read, check and write as one step
            documents = self.__load()
            position = next((i for i, d in enumerate(documents) if d.get("shipment_id") == shipment_id), None)
            if position is None:
                raise StorageError(f"{shipment_id} is not saved, so it cannot be replaced")
            documents[position] = self.__serializer.to_document(record)
            self.__write(documents)

    def find(self, criteria: SearchCriteria) -> List[ShipmentRecord]:
        records = self.__serializer.from_documents(self.__load())
        matching = [r for r in records if criteria.matches(r)]
        return self.__newest_first(matching)

    def find_route_history(self, route_id: str, since: datetime) -> List[ShipmentRecord]:
        if since.tzinfo is None:
            raise ValueError("since must be timezone-aware")
        records = self.__serializer.from_documents(self.__load())
        matching = [r for r in records if r.shipment.route_id() == route_id
                    and r.saved_at >= since and not r.assessment.is_fallback()]
        return self.__newest_first(matching)

    def __newest_first(self, records):
        return sorted(records, key=lambda r: (r.saved_at, r.shipment.shipment_id), reverse=True)

    def __load(self):
        if not self.__path.exists():
            return []
        try:
            documents = json.loads(self.__path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(f"Cannot read {self.__path.name}: {error}") from error
        if not isinstance(documents, list):
            raise StorageError(f"{self.__path.name} is not a list of records")
        return documents

    def __write(self, documents):
        temp = None
        try:
            handle, temp = tempfile.mkstemp(dir=self.__path.parent, prefix=self.__path.stem + ".",
                                            suffix=".json.tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(documents, file, indent=2)
            os.replace(temp, self.__path)
        except OSError as error:
            if temp and os.path.exists(temp):
                os.remove(temp)
            raise StorageError(f"Cannot write {self.__path.name}: {error}") from error
