from datetime import date, datetime, timezone
from pymongo.errors import DuplicateKeyError, PyMongoError
from model.ai_status import AIStatus
from model.storage_error import StorageError
from .data_manager import DataManager
from .record_serializer import RecordSerializer


class MongoDataManager(DataManager):
    """Keeps records in a MongoDB collection. Departure, arrival and saved_at are stored as real dates."""

    def __init__(self, collection, ports):
        self.__collection = collection
        self.__serializer = RecordSerializer(ports)
        try:
            collection.create_index("shipment_id", unique=True)
        except PyMongoError as error:
            raise StorageError(f"Cannot reach the database: {error}") from error

    @classmethod
    def connect(cls, uri, db_name, ports):
        """Open a collection from a connection string. Nothing is read from the environment here."""
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        return cls(client[db_name]["records"], ports)

    def save(self, record):
        document = self.__with_real_dates(self.__serializer.to_document(record))
        try:
            self.__collection.insert_one(document)
        except DuplicateKeyError as error:
            raise StorageError(f"{record.shipment.shipment_id} is already saved") from error
        except PyMongoError as error:
            raise StorageError(f"Cannot save the record: {error}") from error

    def find(self, criteria):
        return self.__find_newest_first(criteria.to_query())

    def find_route_history(self, route_id: str, since: datetime) -> list:
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
