from datetime import date, datetime, timezone
import pytest
from helpers import PORTS, saved_record
from data_layer.record_serializer import RecordSerializer
from io_layer.storage_error import StorageError


def test_a_record_survives_a_round_trip():
    serializer = RecordSerializer(PORTS)
    original = saved_record("SHP-004", risk="HIGH", needs_human=True, fallback=True)
    copy = serializer.from_document(serializer.to_document(original))
    assert copy.shipment == original.shipment
    assert copy.assessment.to_dict() == original.assessment.to_dict()
    assert copy.assessment.is_fallback()
    assert copy.decision.to_dict() == original.decision.to_dict()
    assert copy.saved_at == original.saved_at


def test_the_document_holds_dates_as_iso_text_and_port_codes():
    doc = RecordSerializer(PORTS).to_document(saved_record())
    assert doc["departure"] == "2026-12-01"
    assert doc["origin"] == "SGSIN"


def test_datetimes_from_mongodb_are_accepted():
    serializer = RecordSerializer(PORTS)
    doc = serializer.to_document(saved_record())
    doc["departure"] = datetime(2026, 12, 1, tzinfo=timezone.utc)
    doc["saved_at"] = datetime(2026, 11, 1, 9, 0)           # MongoDB returns naive UTC
    record = serializer.from_document(doc)
    assert record.shipment.departure == date(2026, 12, 1)
    assert record.saved_at.tzinfo is not None


@pytest.mark.parametrize("damage", [{"origin": "ZZZZZ"}, {"departure": "01/12/2026"}, {"decision": None}])
def test_a_damaged_document_is_a_storage_error(damage):
    serializer = RecordSerializer(PORTS)
    doc = {**serializer.to_document(saved_record()), **damage}
    with pytest.raises(StorageError):
        serializer.from_document(doc)


def test_a_missing_field_is_a_storage_error():
    serializer = RecordSerializer(PORTS)
    doc = serializer.to_document(saved_record())
    del doc["assessment"]
    with pytest.raises(StorageError):
        serializer.from_document(doc)
