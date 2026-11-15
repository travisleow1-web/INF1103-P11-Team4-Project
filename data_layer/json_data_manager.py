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
    """Keeps records in one JSON file; needs no database, so it is the default. Use one per file.

    The web server handles requests on several threads, so saves are serialised with a lock.
    """

    def __init__(self, path: Union[str, Path], ports: PortRegistry):
        self.__path, self.__serializer, self.__lock = Path(path), RecordSerializer(ports), threading.Lock()

    def save(self, record: ShipmentRecord) -> None:
        """Add the record to the file. A shipment_id that is already saved is a StorageError."""
        shipment_id = record.shipment.shipment_id
        with self.__lock:                      # read, check and write as one step
            documents = self.__load()
            if any(d.get("shipment_id") == shipment_id for d in documents):
                raise StorageError(f"{shipment_id} is already saved")
            self.__write(documents + [self.__serializer.to_document(record)])

    def find(self, criteria: SearchCriteria) -> List[ShipmentRecord]:
        """The records that match, newest first. Damaged records are skipped and logged."""
        return self.__newest_first(r for r in self.__serializer.from_documents(self.__load()) if criteria.matches(r))

    def find_route_history(self, route_id: str, since: datetime) -> List[ShipmentRecord]:
        """Records on the route saved at or after since, skipping FALLBACK assessments, newest first."""
        if since.tzinfo is None:
            raise ValueError("since must be timezone-aware")
        return self.__newest_first(r for r in self.__serializer.from_documents(self.__load())
                                   if r.shipment.route_id() == route_id and r.saved_at >= since
                                   and not r.assessment.is_fallback())

    def __newest_first(self, records):
        return sorted(records, key=lambda r: (r.saved_at, r.shipment.shipment_id), reverse=True)

    def __load(self):
        """Return the saved documents. A missing file is empty; an unreadable one is an error."""
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
        """Write a temp file next to the real one, then swap it in, so readers never see half a file."""
        temp = None
        try:
            handle, temp = tempfile.mkstemp(dir=self.__path.parent, prefix=self.__path.stem + ".", suffix=".json.tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump(documents, file, indent=2)
            os.replace(temp, self.__path)
        except OSError as error:
            if temp and os.path.exists(temp):
                os.remove(temp)
            raise StorageError(f"Cannot write {self.__path.name}: {error}") from error
