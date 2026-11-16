"""One results page's view of the AI's progress."""
from queue import Queue
from typing import Iterable
from model.fetch_event import FetchEvent
from model.fetch_listener import FetchListener


class StatusFeed(FetchListener):
    """Passes the AI status events of the given shipments to a queue, and ignores everyone else's.

    The AI manager is shared by every request, so each results page adds its own feed while it runs and
    keeps only the events of its own shipments.
    """

    def __init__(self, shipment_ids: Iterable[str], out: Queue):
        self.__ids = frozenset(shipment_ids)
        self.__out = out

    def on_event(self, event: FetchEvent) -> None:
        """Queue the event as ("status", event) if it belongs to this page's shipments."""
        if event.shipment_id in self.__ids:
            self.__out.put(("status", event))
