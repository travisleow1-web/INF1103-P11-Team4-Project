import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import requests
from model.shipment import Shipment
from .ai_settings import HTTP_TIMEOUT

log = logging.getLogger(__name__)


class ContextProvider(ABC):
    def __init__(self, name: str, http: Optional[requests.Session] = None, timeout: float = HTTP_TIMEOUT):
        self.__name = name
        # One Session per feed is shared by every request thread. That is acceptable here: it only pools
        # connections, and holds no cookies or auth state (the feeds need no login).
        self.__http = http or requests.Session()
        self.__timeout = timeout

    @property
    def name(self) -> str:
        return self.__name

    def fetch(self, shipment: Shipment) -> Optional[Any]:
        try:
            return self._request(shipment)
        except Exception as error:      # deliberate: no feed failure may stop an assessment
            log.warning("%s feed failed for %s: %s", self.__name, shipment.shipment_id, error)
            return None

    @abstractmethod
    def _request(self, shipment: Shipment) -> Any:
        ...

    def _get_json(self, url: str, params: Dict[str, Any]) -> Any:
        reply = self.__http.get(url, params=params, timeout=self.__timeout)
        if reply.status_code != 200:
            raise RuntimeError(f"HTTP {reply.status_code} from {url}")
        return reply.json()
