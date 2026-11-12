import logging
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional, Tuple
from data_layer.data_manager import DataManager
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
