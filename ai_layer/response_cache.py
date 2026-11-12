import hashlib
import json
import logging
import os
import tempfile
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union
from model.shipment import Shipment

log = logging.getLogger(__name__)


class ResponseCache:
    """A JSON file of raw model replies, keyed by route, dates, the UTC day and the client fingerprint.

    Each entry records the UTC day it was made for; entries from other days are dropped when the
    file is loaded and when a new entry is added, so the file holds one day at most. An unreadable
    file counts as empty and a failed write is logged, so the cache can never stop an assessment.
    One lock guards the entries and the file, because web requests run in several threads.
    """

    def __init__(self, path: Union[str, Path], version: str):
        self.__path = Path(path)
        self.__version = version          # GeminiClient.fingerprint()
        self.__entries: Optional[Dict[str, Any]] = None
        self.__lock = threading.Lock()

    def make_key(self, shipment: Shipment, today: date) -> str:
        """Key for this shipment's route and dates on `today`, the current UTC date.

        The shipment ID is left out, so two shipments on the same route and dates share a reply.
        """
        details = {"origin": shipment.origin.code, "destination": shipment.destination.code,
                   "departure": shipment.departure.isoformat(), "arrival": shipment.arrival.isoformat()}
        payload = json.dumps(details, sort_keys=True) + f"|{today.isoformat()}|{self.__version}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """The stored entry ({"day", "result": raw reply, "fetched_at": ISO text}) or None."""
        with self.__lock:
            return self.__load().get(key)

    def set(self, key: str, raw: Dict[str, Any], fetched_at: str, day: date) -> None:
        """Store a raw reply made for UTC `day`, drop other days' entries, and write the file."""
        with self.__lock:
            entries = self.__keep_day(self.__load(), day)
            entries[key] = {"day": day.isoformat(), "result": raw, "fetched_at": fetched_at}
            self.__entries = entries
            self.__save(entries)

    @staticmethod
    def __keep_day(entries: Dict[str, Any], day: date) -> Dict[str, Any]:
        text = day.isoformat()
        return {key: entry for key, entry in entries.items()
                if isinstance(entry, dict) and entry.get("day") == text}

    def __load(self) -> Dict[str, Any]:
        if self.__entries is None:
            data: Any = {}
            if self.__path.exists():
                try:
                    with open(self.__path, encoding="utf-8") as f:
                        data = json.load(f)
                except (OSError, ValueError) as error:
                    log.warning("Could not read AI cache %s: %s", self.__path, error)
            if not isinstance(data, dict):
                log.warning("AI cache %s is not a JSON object; starting empty", self.__path)
                data = {}
            self.__entries = self.__keep_day(data, datetime.now(timezone.utc).date())
        return self.__entries

    def __save(self, entries: Dict[str, Any]) -> None:
        temp = None
        try:
            # A unique temp file per write, so two processes never write the same one.
            handle, temp = tempfile.mkstemp(prefix=self.__path.name + ".", suffix=".tmp",
                                            dir=str(self.__path.parent))
            with os.fdopen(handle, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2)
            os.replace(temp, self.__path)
            temp = None
        except (OSError, TypeError, ValueError) as error:
            log.warning("Could not write AI cache %s: %s", self.__path, error)
        finally:
            if temp is not None:
                try:
                    os.remove(temp)
                except OSError:
                    pass
