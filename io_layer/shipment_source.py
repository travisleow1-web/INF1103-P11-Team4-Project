from abc import ABC, abstractmethod


class ShipmentSource(ABC):
    @abstractmethod
    def read(self) -> "list[dict]":
        ...
