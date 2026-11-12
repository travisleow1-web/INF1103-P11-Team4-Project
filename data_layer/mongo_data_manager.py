from datetime import date, datetime, timezone
from typing import List
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError
from model.ai_status import AIStatus
from model.port_registry import PortRegistry
from model.search_criteria import SearchCriteria
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError
from .data_manager import DataManager
from .record_serializer import RecordSerializer


class MongoDataManager(DataManager):
    """Keeps records in a MongoDB collection. Departure, arrival and saved_at are stored as real dates."""

    def __init__(self, collection: Collection, ports: PortRegistry):
        """Use an open collection (mongomock in tests). Makes shipment_id unique."""
        self.__collection = collection
        self.__serializer = RecordSerializer(ports)
        try:
            collection.create_index("shipment_id", unique=True)
        except PyMongoError as error:
            raise StorageError(f"Cannot reach the database: {error}") from error

    @classmethod
    def connect(cls, uri: str, db_name: str, ports: PortRegistry, collection_name: str = "shipment_records") -> "MongoDataManager":
        """Open a collection from a connection string. Nothing is read from the environment here.

        Raises StorageError if the address is invalid or the server cannot be reached.
        """
        from pymongo import MongoClient
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        except PyMongoError as error:
            raise StorageError(f"Cannot reach the database: {error}") from error
        return cls(client[db_name][collection_name], ports)

    def save(self, record: ShipmentRecord) -> None:
        """Insert the record. A shipment_id that is already saved is a StorageError."""
        document = self.__with_real_dates(self.__serializer.to_document(record))
        try:
            self.__collection.insert_one(document)
        except DuplicateKeyError as error:
            raise StorageError(f"{record.shipment.shipment_id} is already saved") from error
        except PyMongoError as error:
            raise StorageError(f"Cannot save the record: {error}") from error

    def find(self, criteria: SearchCriteria) -> List[ShipmentRecord]:
        """The records that match, newest first."""
        return self.__find_newest_first(criteria.to_query())

    def find_route_history(self, route_id: str, since: datetime) -> List[ShipmentRecord]:
        """Records on the route saved at or after since, skipping FALLBACK assessments, newest first."""
        origin, _, destination = route_id.partition("-")
        return self.__find_newest_first({
            "origin": origin,
            "destination": destination,
            "saved_at": {"$gte": since},
            "assessment.ai_status": {"$ne": AIStatus.FALLBACK.value},
        })

    def __find_newest_first(self, query):
        try:
            cursor = self.__collection.find(query)
            documents = list(cursor.sort([("saved_at", -1), ("shipment_id", -1)]))
        except PyMongoError as error:
            raise StorageError(f"Cannot search the database: {error}") from error
        return [self.__serializer.from_document(d) for d in documents]

    def __with_real_dates(self, document):
        """MongoDB cannot store a bare date, so days become midnight UTC datetimes."""
        for key in ("departure", "arrival"):
            day = date.fromisoformat(document[key])
            document[key] = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        document["saved_at"] = datetime.fromisoformat(document["saved_at"])
        return document
