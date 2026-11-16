from abc import ABC, abstractmethod
from .fetch_event import FetchEvent


class FetchListener(ABC):
    """Something that wants to hear how an AI fetch is going: a console printer, a log, a web page.

    The AI manager only knows this interface, so a new way of showing status needs no change to it.
    """

    @abstractmethod
    def on_event(self, event: FetchEvent) -> None:
        """Handle one status event. Several request threads may call this at the same time."""
