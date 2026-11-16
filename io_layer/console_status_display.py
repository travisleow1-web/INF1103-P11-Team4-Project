import sys
import threading
from typing import Optional, TextIO
from model.fetch_event import FetchEvent
from model.fetch_listener import FetchListener
from model.fetch_stage import FetchStage


class ConsoleStatusDisplay(FetchListener):
    """Prints one line per AI fetch event, for example '[SHP-001] AI: fetching in progress...'.

    This is the only class that prints status. The AI manager just reports events, and IOManager
    still never prints. Lines carry the shipment ID because requests run in several threads.
    """

    __MESSAGES = {
        FetchStage.CACHE_HIT: "using saved assessment (cache)",
        FetchStage.STARTED: "fetching in progress...",
        FetchStage.RETRYING: "attempt {attempt}/{max_attempts} failed ({detail}), trying again...",
        FetchStage.SUCCEEDED: "fetching complete",
        FetchStage.FAILED: "fetching failed ({detail}), using fallback assessment",
    }

    def __init__(self, out: Optional[TextIO] = None):
        self.__out = out                    # None means sys.stdout at the time of printing
        self.__lock = threading.Lock()      # keeps lines from different threads from mixing

    def on_event(self, event: FetchEvent) -> None:
        """Print the event as one line."""
        with self.__lock:
            print(self.__format(event), file=self.__out or sys.stdout, flush=True)

    def __format(self, event: FetchEvent) -> str:
        message = self.__MESSAGES[event.stage].format(
            attempt=event.attempt, max_attempts=event.max_attempts, detail=event.detail or "no details")
        return f"[{event.shipment_id}] AI: {message}"
