"""FetchEvent.describe (the wording shared by the console and the web page) and adding or removing listeners."""
import pytest
from ai_helpers import make_shipment
from test_ai_manager import make_manager, mock_client
from model.fetch_event import FetchEvent
from model.fetch_listener import FetchListener
from model.fetch_stage import FetchStage


class Recorder(FetchListener):
    def __init__(self):
        self.stages = []

    def on_event(self, event):
        self.stages.append(event.stage)


@pytest.mark.parametrize("event, words", [
    (FetchEvent("SHP-001", FetchStage.CACHE_HIT), "using saved assessment (cache)"),
    (FetchEvent("SHP-001", FetchStage.STARTED), "fetching in progress..."),
    (FetchEvent("SHP-001", FetchStage.RETRYING, 1, 3, "HTTP 503"), "attempt 1/3 failed (HTTP 503), trying again..."),
    (FetchEvent("SHP-001", FetchStage.SUCCEEDED), "fetching complete"),
    (FetchEvent("SHP-001", FetchStage.FAILED, detail="timeout"), "fetching failed (timeout), using fallback assessment"),
    (FetchEvent("SHP-001", FetchStage.FAILED), "fetching failed (no details), using fallback assessment"),
])
def test_each_stage_is_described_in_words(event, words):
    assert event.describe() == words


def test_a_listener_added_later_hears_the_fetch(tmp_path):
    manager = make_manager(tmp_path, mock_client())
    heard = Recorder()
    manager.add_listener(heard)
    manager.assess(make_shipment())
    assert heard.stages == [FetchStage.STARTED, FetchStage.SUCCEEDED]


def test_a_removed_listener_hears_nothing_more(tmp_path):
    manager = make_manager(tmp_path, mock_client())
    heard = Recorder()
    manager.add_listener(heard)
    manager.remove_listener(heard)
    manager.assess(make_shipment())
    assert heard.stages == []


def test_removing_a_listener_that_was_never_added_is_ignored(tmp_path):
    make_manager(tmp_path, mock_client()).remove_listener(Recorder())


def test_a_listener_may_remove_itself_while_it_is_being_told(tmp_path):
    manager = make_manager(tmp_path, mock_client())
    other = Recorder()

    class OneShot(Recorder):
        def on_event(self, event):
            super().on_event(event)
            manager.remove_listener(self)
    first = OneShot()
    manager.add_listener(first)
    manager.add_listener(other)
    manager.assess(make_shipment())
    assert first.stages == [FetchStage.STARTED] and other.stages == [FetchStage.STARTED, FetchStage.SUCCEEDED]
