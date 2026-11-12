import time
from typing import Any, Dict, List, Optional
import requests
from model.shipment import Shipment
from .ai_settings import NEWS_MIN_GAP
from .context_provider import ContextProvider

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


class NewsProvider(ContextProvider):
    """Recent English headlines about piracy, congestion, strikes or unrest at the two ports (GDELT).

    GDELT allows one call every few seconds, so the provider remembers when it last called and
    waits only for the rest of the gap.
    """

    def __init__(self, http: Optional[requests.Session] = None, min_gap: float = NEWS_MIN_GAP):
        super().__init__("news", http)
        self.__min_gap = min_gap
        self.__last_call: Optional[float] = None

    def _request(self, shipment: Shipment) -> List[Dict[str, Any]]:
        self.__wait_for_gap()
        query = (f'("{shipment.origin.name}" OR "{shipment.destination.name}")'
                 ' (piracy OR "armed robbery" OR "port congestion" OR strike OR protest OR unrest)'
                 ' sourcelang:english')
        params = {"query": query, "mode": "ArtList", "maxrecords": 8, "format": "json", "timespan": "3d"}
        articles = self._get_json(GDELT_URL, params).get("articles", [])
        return [{"title": a["title"], "seen": a["seendate"]} for a in articles]

    def __wait_for_gap(self) -> None:
        if self.__last_call is not None:
            remaining = self.__min_gap - (time.monotonic() - self.__last_call)
            if remaining > 0:
                time.sleep(remaining)
        self.__last_call = time.monotonic()
