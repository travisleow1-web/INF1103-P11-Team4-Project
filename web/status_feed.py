from queue import Queue
from typing import Iterable
from model.fetch_event import FetchEvent
from model.fetch_listener import FetchListener


class StatusFeed(FetchListener):
    def __init__(self, shipment_ids: Iterable[str], out: Queue):
        self.__ids = frozenset(shipment_ids)
        self.__out = out

    def on_event(self, event: FetchEvent) -> None:
        if event.shipment_id in self.__ids:
            self.__out.put(("status", event))
