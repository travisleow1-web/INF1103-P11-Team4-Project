from abc import ABC, abstractmethod
from .fetch_event import FetchEvent


class FetchListener(ABC):
    @abstractmethod
    def on_event(self, event: FetchEvent) -> None:
        ...
