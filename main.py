from datetime import datetime, timezone
from model.shipment_record import ShipmentRecord


def assess_shipments(shipments, ai, logic, data):
    """Assess, decide and save one shipment at a time, yielding each record as soon as it is saved."""
    for shipment in shipments:
        assessment = ai.assess(shipment)
        decision = logic.evaluate(shipment, assessment, datetime.now(timezone.utc))
        record = ShipmentRecord(shipment, assessment, decision)
        data.save(record)
        yield record
