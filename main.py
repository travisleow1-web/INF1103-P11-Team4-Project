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
from web.app import create_web_app

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
    """The AI manager built from GEMINI_API_KEY, or None when no key is set.

    GEMINI_MODEL picks the model and AI_CACHE_FILE the cache file (default ai_cache.json).
    """
    from ai_layer.ai_manager import AIManager
    from ai_layer.ai_settings import ALLOWED_LISTS, DEFAULT_MODEL, RESPONSE_SCHEMA, SYSTEM_PROMPT
    from ai_layer.gemini_client import GeminiClient
    from ai_layer.news_provider import NewsProvider
    from ai_layer.weather_provider import WeatherProvider

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    client = GeminiClient(key, os.getenv("GEMINI_MODEL") or DEFAULT_MODEL, SYSTEM_PROMPT, RESPONSE_SCHEMA)
    return AIManager(client, [WeatherProvider(), NewsProvider()],
                     os.getenv("AI_CACHE_FILE") or "ai_cache.json", ALLOWED_LISTS)


def build_logic(data: DataManager, ports: PortRegistry):
    """The Logic manager with the default rule thresholds. Route history comes from data."""
    from logic_layer.logic_manager import LogicManager

    return LogicManager(data, ports)


def build_data(ports: PortRegistry) -> DataManager:
    """The storage backend chosen by DATA_BACKEND: 'json' (default, DATA_FILE) or 'mongo' (MONGO_URI, DB_NAME).

    If MongoDB cannot be reached, the app still starts with an UnavailableDataManager holding the reason.
    """
    backend = (os.getenv("DATA_BACKEND") or "json").strip().lower()
    if backend == "json":
        return JsonDataManager(os.getenv("DATA_FILE") or "shipment_records.json", ports)
    if backend == "mongo":
        try:
            return build_mongo(ports)
        except StorageError as error:
            logger.error("Starting without storage: %s", error)
            return UnavailableDataManager(MongoDataManager.UNAVAILABLE)
    raise ValueError(f"DATA_BACKEND must be 'json' or 'mongo', not {backend!r}")


def build_mongo(ports: PortRegistry) -> MongoDataManager:
    """Connect to the MongoDB named by MONGO_URI and DB_NAME. Raises StorageError if that fails."""
    uri, db_name = os.getenv("MONGO_URI", "").strip(), os.getenv("DB_NAME", "").strip()
    if not uri or not db_name:
        raise StorageError("MONGO_URI and DB_NAME must both be set to use MongoDB")
    return MongoDataManager.connect(uri, db_name, ports)


def create_app() -> FastAPI:
    """Set up logging if nothing has, read .env, compose the managers and return the FastAPI app.

    DEMO_MODE=1 uses the fake AI and Logic from tests/fakes.py and keeps its records in DEMO_DATA_FILE
    (default demo_records.json), never in MongoDB or DATA_FILE. Every page then shows a demo banner.
    """
    if not logging.getLogger().handlers:        # leave a host's own logging setup alone
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()
    ports = PortRegistry.from_json()
    demo = os.getenv("DEMO_MODE", "").strip() == "1"
    if demo:
        from tests.fakes import FakeAI, FakeLogic
        data = JsonDataManager(os.getenv("DEMO_DATA_FILE") or "demo_records.json", ports)
        ai, logic = FakeAI(), FakeLogic()
    else:
        data = build_data(ports)
        ai, logic = build_ai(), build_logic(data, ports)
    io = IOManager(ShipmentValidator(ports), data, ports)
    notices = [data.message] if isinstance(data, UnavailableDataManager) else []
    return create_web_app(io, ai, logic, data, demo, notices, run=assess_shipments)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:create_app", factory=True, host="127.0.0.1", port=8000)
