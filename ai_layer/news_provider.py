import logging
import threading
import time
from typing import Any, Dict, List, Optional
import requests
from model.shipment import Shipment
from .ai_settings import NEWS_FAILURES_BEFORE_PAUSE, NEWS_MIN_GAP, NEWS_PAUSE, NEWS_TIMEOUT
from .context_provider import ContextProvider

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

log = logging.getLogger(__name__)


class NewsProvider(ContextProvider):
    def __init__(self, http: Optional[requests.Session] = None, min_gap: float = NEWS_MIN_GAP,
                 timeout: float = NEWS_TIMEOUT, pause_after: int = NEWS_FAILURES_BEFORE_PAUSE,
                 pause_for: float = NEWS_PAUSE):
        super().__init__("news", http, timeout)
        self.__min_gap = min_gap
        self.__pause_after = pause_after
        self.__pause_for = pause_for
        self.__last_call: Optional[float] = None
        self.__failures = 0                     # failed calls in a row
        self.__paused_until: Optional[float] = None
        self.__lock = threading.Lock()          # web requests run in several threads

    def _request(self, shipment: Shipment) -> Optional[List[Dict[str, Any]]]:
        if self.__is_paused():
            return None                         # no call, no wait: the AI runs without news for now
        self.__wait_for_gap()
        query = (f'("{shipment.origin.name}" OR "{shipment.destination.name}")'
                 ' (piracy OR "armed robbery" OR "port congestion" OR strike OR protest OR unrest)'
                 ' sourcelang:english')
        params = {"query": query, "mode": "ArtList", "maxrecords": 8, "format": "json", "timespan": "3d"}
        try:
            articles = self._get_json(GDELT_URL, params).get("articles", [])
            result = [{"title": a["title"], "seen": a["seendate"]} for a in articles]
        except Exception:                       # fetch() logs it and gives None; here it only counts the failure
            self.__record_failure()
            raise
        self.__failures = 0
        return result

    def __is_paused(self) -> bool:
        if self.__paused_until is None:
            return False
        if time.monotonic() < self.__paused_until:
            return True
        self.__paused_until = None              # the pause is over: try GDELT again
        return False

    def __record_failure(self) -> None:
        with self.__lock:
            self.__failures += 1
            if self.__failures >= self.__pause_after:
                self.__failures = 0
                self.__paused_until = time.monotonic() + self.__pause_for
                log.warning("GDELT failed %d times in a row; skipping news for %d seconds",
                            self.__pause_after, self.__pause_for)

    def __wait_for_gap(self) -> None:
        with self.__lock:                       # held while sleeping, so callers queue up
            if self.__last_call is not None:
                remaining = self.__min_gap - (time.monotonic() - self.__last_call)
                if remaining > 0:
                    time.sleep(remaining)
            self.__last_call = time.monotonic()
