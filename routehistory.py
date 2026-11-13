"""RouteHistorySource interface and its Data Manager adapter."""

from abc import ABC, abstractmethod


class RouteHistorySource(ABC):
    """Contract: anything that can list past shipments on a route since a given time."""

    @abstractmethod
    def get_route_history(self, route_id, since):
        """Return a list of past-run dicts; a run may carry 'flagged' / 'delayed' booleans."""


class DataManagerRouteHistory(RouteHistorySource):
    """Adapts the Data Manager's stored records to the RouteHistorySource interface."""

    def __init__(self, db_records):
        self._db_records = db_records

    def get_route_history(self, route_id, since):
        import data_manager  # imported here so the Logic Manager can be tested without it
        return data_manager.get_route_history(self._db_records, route_id, since)
