"""Composition root: the only module that knows every manager.

Run the web app with:  uvicorn main:Application.create --factory
"""
import logging
import os
from typing import TYPE_CHECKING, Optional
from dotenv import load_dotenv
from fastapi import FastAPI
from assessment_pipeline import AssessmentPipeline
from data_layer.data_manager import DataManager
from data_layer.json_data_manager import JsonDataManager
from data_layer.mongo_data_manager import MongoDataManager
from data_layer.unavailable_data_manager import UnavailableDataManager
from io_layer.io_manager import IOManager
from io_layer.shipment_validator import ShipmentValidator
from model.port_registry import PortRegistry
from model.storage_error import StorageError
from web.app import create_web_app

if TYPE_CHECKING:       # for type hints only; the layers are imported inside build_ai and build_logic
    from ai_layer.ai_manager import AIManager
    from logic_layer.logic_manager import LogicManager

logger = logging.getLogger(__name__)


class Application:
    """Reads the settings from the environment (and .env) and wires the four managers into the web app.

    It is the only class that knows every manager. Each build_* method makes one manager, so a new
    storage backend or AI provider changes only the method that builds it.
    """

    @classmethod
    def create(cls) -> FastAPI:
        """The uvicorn factory: build a new Application and return its web app."""
        return cls().create_app()

    def create_app(self) -> FastAPI:
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
            data = self.build_data(ports)
            ai, logic = self.build_ai(), self.build_logic(data, ports)
        io = IOManager(ShipmentValidator(ports), data, ports)
        notices = [data.message] if isinstance(data, UnavailableDataManager) else []
        pipeline = AssessmentPipeline(ai, logic, data)
        return create_web_app(io, ai, logic, demo, notices, run=pipeline.run)

    def build_ai(self) -> Optional["AIManager"]:
        """The AI manager built from GEMINI_API_KEY, or None when no key is set.

        GEMINI_MODEL picks the model and AI_CACHE_FILE the cache file (default ai_cache.json).
        """
        from ai_layer.ai_manager import AIManager
        from ai_layer.ai_settings import ALLOWED_LISTS, DEFAULT_MODEL, RESPONSE_SCHEMA, SYSTEM_PROMPT
        from ai_layer.gemini_client import GeminiClient
        from ai_layer.news_provider import NewsProvider
        from ai_layer.weather_provider import WeatherProvider
        from io_layer.console_status_display import ConsoleStatusDisplay

        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            return None
        client = GeminiClient(key, os.getenv("GEMINI_MODEL") or DEFAULT_MODEL, SYSTEM_PROMPT, RESPONSE_SCHEMA)
        return AIManager(client, [WeatherProvider(), NewsProvider()],
                         os.getenv("AI_CACHE_FILE") or "ai_cache.json", ALLOWED_LISTS,
                         listeners=[ConsoleStatusDisplay()])

    def build_logic(self, data: DataManager, ports: PortRegistry) -> "LogicManager":
        """The Logic manager with the default rule thresholds. Route history comes from data."""
        from logic_layer.logic_manager import LogicManager

        return LogicManager(data, ports)

    def build_data(self, ports: PortRegistry) -> DataManager:
        """The storage backend chosen by DATA_BACKEND: 'json' (default, DATA_FILE) or 'mongo' (MONGO_URI, DB_NAME).

        If MongoDB cannot be reached, the app still starts with an UnavailableDataManager holding the reason.
        """
        backend = (os.getenv("DATA_BACKEND") or "json").strip().lower()
        if backend == "json":
            return JsonDataManager(os.getenv("DATA_FILE") or "shipment_records.json", ports)
        if backend == "mongo":
            try:
                return self.__build_mongo(ports)
            except StorageError as error:
                logger.error("Starting without storage: %s", error)
                return UnavailableDataManager(MongoDataManager.UNAVAILABLE)
        raise ValueError(f"DATA_BACKEND must be 'json' or 'mongo', not {backend!r}")

    def __build_mongo(self, ports: PortRegistry) -> MongoDataManager:
        """Connect to the MongoDB named by MONGO_URI and DB_NAME. Raises StorageError if that fails."""
        uri, db_name = os.getenv("MONGO_URI", "").strip(), os.getenv("DB_NAME", "").strip()
        if not uri or not db_name:
            raise StorageError("MONGO_URI and DB_NAME must both be set to use MongoDB")
        return MongoDataManager.connect(uri, db_name, ports)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:Application.create", factory=True, host="127.0.0.1", port=8000)
