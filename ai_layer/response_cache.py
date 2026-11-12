import hashlib
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union
from model.shipment import Shipment

log = logging.getLogger(__name__)


class ResponseCache:
    """A JSON file of raw model replies, keyed by route, dates, the UTC day and the client fingerprint.

    The file is read the first time it is needed. An unreadable file counts as empty, and a failed
    write is logged, so the cache can never stop an assessment.
    """

    def __init__(self, path: Union[str, Path], version: str):
        self.__path = Path(path)
        self.__version = version          # GeminiClient.fingerprint()
        self.__entries: Optional[Dict[str, Any]] = None

    def make_key(self, shipment: Shipment, today: Optional[date] = None) -> str:
        """Key for this shipment's route and dates on `today` (default: the current UTC date).

        The shipment ID is left out, so two shipments on the same route and dates share a reply.
        """
        today = today or datetime.now(timezone.utc).date()
        details = {"origin": shipment.origin.code, "destination": shipment.destination.code,
                   "departure": shipment.departure.isoformat(), "arrival": shipment.arrival.isoformat()}
        payload = json.dumps(details, sort_keys=True) + f"|{today.isoformat()}|{self.__version}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """The stored entry ({"result": raw reply, "fetched_at": ISO text}) or None."""
        return self.__load().get(key)

    def set(self, key: str, raw: Dict[str, Any], fetched_at: str) -> None:
        """Store a raw reply with its fetch time and write the file."""
        entries = self.__load()
        entries[key] = {"result": raw, "fetched_at": fetched_at}
        self.__save(entries)

    def __load(self) -> Dict[str, Any]:
        if self.__entries is None:
            self.__entries = {}
            if self.__path.exists():
                try:
                    with open(self.__path, encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self.__entries = data
                    else:
                        log.warning("AI cache %s is not a JSON object; starting empty", self.__path)
                except (OSError, ValueError) as error:
                    log.warning("Could not read AI cache %s: %s", self.__path, error)
        return self.__entries

    def __save(self, entries: Dict[str, Any]) -> None:
        temp = self.__path.with_name(self.__path.name + ".tmp")
        try:
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2)
            os.replace(temp, self.__path)
        except (OSError, TypeError, ValueError) as error:
            log.warning("Could not write AI cache %s: %s", self.__path, error)
