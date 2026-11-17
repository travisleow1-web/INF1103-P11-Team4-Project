import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable, Iterator, Optional, Tuple
from data_layer.data_manager import DataManager
from model.shipment import Shipment
from model.shipment_record import ShipmentRecord
from model.storage_error import StorageError

if TYPE_CHECKING:       # for type hints only; the layers are imported inside main.build_ai and main.build_logic
    from ai_layer.ai_manager import AIManager
    from logic_layer.logic_manager import LogicManager

logger = logging.getLogger(__name__)


class AssessmentPipeline:
    def __init__(self, ai: "AIManager", logic: "LogicManager", data: DataManager):
        self.__ai = ai
        self.__logic = logic
        self.__data = data

    def run(self, shipments: Iterable[Shipment],
            replace: bool = False) -> Iterator[Tuple[ShipmentRecord, Optional[str]]]:
        store = self.__data.replace if replace else self.__data.save
        for shipment in shipments:
            assessment = self.__ai.assess(shipment)
            decision = self.__logic.evaluate(shipment, assessment, datetime.now(timezone.utc))
            record = ShipmentRecord(shipment, assessment, decision)
            save_error = None
            try:
                store(record)
            except StorageError as error:
                save_error = str(error)
                logger.warning("%s was not saved: %s", shipment.shipment_id, error)
            yield record, save_error
