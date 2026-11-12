"""Composition root: the only module that knows every manager.

Run the web app with:  uvicorn main:create_app --factory
"""
import logging
import os
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional, Tuple
from dotenv import load_dotenv
from fastapi import FastAPI
from data_layer.data_manager import DataManager
from data_layer.json_data_manager import JsonDataManager
from data_layer.mongo_data_manager import MongoDataManager
from data_layer.unavailable_data_manager import UnavailableDataManager
from io_layer.io_manager import IOManager
from io_layer.shipment_validator import ShipmentValidator
from model.port_registry import PortRegistry
from model.shipment import Shipment
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError

logger = logging.getLogger(__name__)


def assess_shipments(shipments: Iterable[Shipment], ai, logic,
                     data: DataManager) -> Iterator[Tuple[ShipmentRecord, Optional[str]]]:
    """Assess, decide and save one shipment at a time, yielding (record, save_error) as each finishes.

    save_error is None when the record was saved, otherwise the reason it was not. A failed save
    does not stop the remaining shipments.
    """
    for shipment in shipments:
        assessment = ai.assess(shipment)
        decision = logic.evaluate(shipment, assessment, datetime.now(timezone.utc))
        record = ShipmentRecord(shipment, assessment, decision)
        save_error = None
        try:
            data.save(record)
        except StorageError as error:
            save_error = str(error)
            logger.warning("%s was not saved: %s", shipment.shipment_id, error)
        yield record, save_error


def build_ai():
    """The AI manager, or None while the AI layer is not connected."""
    return None


def build_logic(data: DataManager, ports: PortRegistry):
    """The Logic manager, or None while the Logic layer is not connected."""
    return None


def build_data(ports: PortRegistry) -> DataManager:
    """The storage backend chosen by DATA_BACKEND: 'json' (default, DATA_FILE) or 'mongo' (MONGO_URI, DB_NAME).

    If MongoDB cannot be reached, the app still starts with an UnavailableDataManager holding the reason.
    """
    backend = os.getenv("DATA_BACKEND", "json").strip().lower()
    if backend == "json":
        return JsonDataManager(os.getenv("DATA_FILE") or "shipment_records.json", ports)
    if backend == "mongo":
        try:
            return build_mongo(ports)
        except StorageError as error:
            logger.error("Starting without storage: %s", error)
            return UnavailableDataManager(f"Database unavailable: {error}. Results will not be saved.")
    raise ValueError(f"DATA_BACKEND must be 'json' or 'mongo', not {backend!r}")


def build_mongo(ports: PortRegistry) -> MongoDataManager:
    """Connect to the MongoDB named by MONGO_URI and DB_NAME. Raises StorageError if that fails."""
    uri, db_name = os.getenv("MONGO_URI", "").strip(), os.getenv("DB_NAME", "").strip()
    if not uri or not db_name:
        raise StorageError("MONGO_URI and DB_NAME must both be set to use MongoDB")
    return MongoDataManager.connect(uri, db_name, ports)


def create_app() -> FastAPI:
    """Read .env, compose the managers and return the FastAPI app.

    DEMO_MODE=1 uses the fake AI and Logic from tests/fakes.py, and every page shows a demo banner.
    """
    from web.app import create_web_app        # here, not at the top: web.app imports assess_shipments

    load_dotenv()
    ports = PortRegistry.from_json()
    data = build_data(ports)
    demo = os.getenv("DEMO_MODE", "").strip() == "1"
    if demo:
        from tests.fakes import FakeAI, FakeLogic
        ai, logic = FakeAI(), FakeLogic()
    else:
        ai, logic = build_ai(), build_logic(data, ports)
    io = IOManager(ShipmentValidator(ports), data, ports)
    notices = [data.message] if isinstance(data, UnavailableDataManager) else []
    return create_web_app(io, ai, logic, data, demo, notices)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:create_app", factory=True, host="127.0.0.1", port=8000)
