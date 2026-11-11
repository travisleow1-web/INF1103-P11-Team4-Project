from abc import ABC, abstractmethod


class ShipmentSource(ABC):
    @abstractmethod
    def read(self):
        """Return a list of raw rows, each one a dict."""
