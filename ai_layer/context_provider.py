import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import requests
from model.shipment import Shipment
from .ai_settings import HTTP_TIMEOUT

log = logging.getLogger(__name__)


class ContextProvider(ABC):
    """One external feed that adds context to the prompt, such as weather or news.

    fetch() never raises: a failed feed is logged and gives None, so the AI still runs without it.
    """

    def __init__(self, name: str, http: Optional[requests.Session] = None, timeout: float = HTTP_TIMEOUT):
        self.__name = name
        self.__http = http or requests.Session()
        self.__timeout = timeout

    @property
    def name(self) -> str:
        """The key this feed's data has in the prompt, for example 'weather'."""
        return self.__name

    def fetch(self, shipment: Shipment) -> Optional[Any]:
        """The feed's data for this shipment, or None if the feed failed."""
        try:
            return self._request(shipment)
        except Exception as error:      # deliberate: no feed failure may stop an assessment
            log.warning("%s feed failed for %s: %s", self.__name, shipment.shipment_id, error)
            return None

    @abstractmethod
    def _request(self, shipment: Shipment) -> Any:
        """Call the feed and return its data. May raise; fetch() catches it."""

    def _get_json(self, url: str, params: Dict[str, Any]) -> Any:
        """GET a URL and return its JSON body. Raises on an HTTP error status or a non-JSON body."""
        reply = self.__http.get(url, params=params, timeout=self.__timeout)
        if reply.status_code != 200:
            raise RuntimeError(f"HTTP {reply.status_code} from {url}")
        return reply.json()
