from abc import ABC, abstractmethod


class ShipmentSource(ABC):
    """Somewhere raw shipment rows come from: a typed form row or an uploaded CSV file."""

    @abstractmethod
    def read(self) -> "list[dict]":
        """Return a list of raw rows, each one a dict of strings. Raise SourceError if it cannot be read."""
