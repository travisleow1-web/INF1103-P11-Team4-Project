import sys
import threading
from typing import Optional, TextIO
from model.fetch_event import FetchEvent
from model.fetch_listener import FetchListener


class ConsoleStatusDisplay(FetchListener):
    def __init__(self, out: Optional[TextIO] = None):
        self.__out = out                    # None means sys.stdout at the time of printing
        self.__lock = threading.Lock()      # keeps lines from different threads from mixing

    def on_event(self, event: FetchEvent) -> None:
        with self.__lock:
            print(self.__format(event), file=self.__out or sys.stdout, flush=True)

    def __format(self, event: FetchEvent) -> str:
        return f"[{event.shipment_id}] AI: {event.describe()}"
