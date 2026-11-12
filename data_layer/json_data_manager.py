import json
import os
from datetime import datetime
from pathlib import Path
from model.storage_error import StorageError
from .data_manager import DataManager
from .record_serializer import RecordSerializer


class JsonDataManager(DataManager):
    """Keeps records in one JSON file. Needs no database, so it is the default."""

    def __init__(self, path, ports):
        self.__path = Path(path)
        self.__serializer = RecordSerializer(ports)

    def save(self, record):
        documents = self.__load()
        shipment_id = record.shipment.shipment_id
        if any(d.get("shipment_id") == shipment_id for d in documents):
            raise StorageError(f"{shipment_id} is already saved")
        documents.append(self.__serializer.to_document(record))
        self.__write(documents)

    def find(self, criteria):
        records = [self.__serializer.from_document(d) for d in self.__load()]
        matching = [r for r in records if criteria.matches(r)]
        return self.__newest_first(matching)

    def find_route_history(self, route_id: str, since: datetime) -> list:
        """Records on the route saved at or after since, skipping FALLBACK assessments, newest first."""
        records = [self.__serializer.from_document(d) for d in self.__load()]
        matching = [r for r in records if r.shipment.route_id() == route_id
                    and r.saved_at >= since and not r.assessment.is_fallback()]
        return self.__newest_first(matching)

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
        """Write to a temporary file first so a crash cannot leave half a file."""
        temp = self.__path.with_name(self.__path.name + ".tmp")
        try:
            temp.write_text(json.dumps(documents, indent=2), encoding="utf-8")
            os.replace(temp, self.__path)
        except OSError as error:
            raise StorageError(f"Cannot write {self.__path.name}: {error}") from error
