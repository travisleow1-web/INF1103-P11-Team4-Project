from datetime import datetime, timezone
import pytest
from data_layer.data_manager import DataManager
from data_layer.unavailable_data_manager import UnavailableDataManager
from model.search_criteria import SearchCriteria
from model.storage_error import StorageError
from helpers import saved_record


def test_it_is_a_data_manager_that_keeps_its_message():
    data = UnavailableDataManager("Cannot reach the database")
    assert isinstance(data, DataManager)
    assert data.message == "Cannot reach the database"


@pytest.mark.parametrize("call", [
    lambda d: d.save(saved_record()),
    lambda d: d.find(SearchCriteria()),
    lambda d: d.find_route_history("SGSIN-NLRTM", datetime(2026, 11, 1, tzinfo=timezone.utc)),
])
def test_every_call_raises_the_message(call):
    with pytest.raises(StorageError, match="^Cannot reach the database$"):
        call(UnavailableDataManager("Cannot reach the database"))


def test_io_search_shows_the_message_instead_of_failing():
    from helpers import make_io
    result = make_io(UnavailableDataManager("Cannot reach the database")).search({})
    assert result == {"kind": "error", "message": "Cannot reach the database"}
