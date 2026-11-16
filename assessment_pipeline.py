"""The assessment flow every shipment goes through: AI, then Logic, then Data."""
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable, Iterator, Optional, Tuple
from data_layer.data_manager import DataManager
from model.shipment import Shipment
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError

if TYPE_CHECKING:       # for type hints only; main.py imports the AI and Logic layers when it builds them
    from ai_layer.ai_manager import AIManager
    from logic_layer.logic_manager import LogicManager

logger = logging.getLogger(__name__)


class AssessmentPipeline:
    """Sends each shipment through the AI, then the business rules, then storage.

    The managers never call each other; this class is the one place that passes one manager's output
    to the next. It holds the three managers (aggregation): they are built by main.Application and
    outlive it.
    """

    def __init__(self, ai: "AIManager", logic: "LogicManager", data: DataManager):
        self.__ai = ai
        self.__logic = logic
        self.__data = data

    def run(self, shipments: Iterable[Shipment]) -> Iterator[Tuple[ShipmentRecord, Optional[str]]]:
        """Assess, decide and save one shipment at a time, yielding (record, save_error) as each finishes.

        save_error is None when the record was saved, otherwise the reason it was not. A failed save
        does not stop the remaining shipments.
        """
        for shipment in shipments:
            assessment = self.__ai.assess(shipment)
            decision = self.__logic.evaluate(shipment, assessment, datetime.now(timezone.utc))
            record = ShipmentRecord(shipment, assessment, decision)
            save_error = None
            try:
                self.__data.save(record)
            except StorageError as error:
                save_error = str(error)
                logger.warning("%s was not saved: %s", shipment.shipment_id, error)
            yield record, save_error
