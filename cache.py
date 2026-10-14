import os
import json
import hashlib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any
from config import CACHE_FILE, SCHEMA_VERSION, TIMEZONE

log = logging.getLogger("ai_manager")
_cache: Optional[Dict[str, Any]] = None

def _load_cache() -> Dict[str, Any]:
    # Load the AI response cache from the specified CACHE_FILE, returning an empty dictionary if the file does not exist or is unreadable.
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Failed to load AI response cache from %s: %s", CACHE_FILE, exc)
        return {}

def _save_cache(cache_data: Dict[str, Any]) -> None:
    # Save the AI response cache to the specified CACHE_FILE, logging a warning if the save operation fails.
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, default=str)
    except Exception as exc:
        log.warning("Failed to save AI response to %s: %s", CACHE_FILE, exc)

def get_cache_key(shipment: Dict[str, Any]) -> str:
    # Generate a unique cache key for a shipment based on its fields, the current date, and the schema version, using SHA-256 hashing.
    today = datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()
    fields = {k: v for k, v in shipment.items() if k != "shipment_id"}
    payload = json.dumps(fields, sort_keys=True, default=str) + f"|{today}|v{SCHEMA_VERSION}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def cache_get(key: str) -> Optional[Dict[str, Any]]:
    # Retrieve a cached AI response for the given key, loading the cache from disk if it has not been loaded yet. Returns None if the key is not found.
    global _cache
    if _cache is None:
        _cache = _load_cache()
    return _cache.get(key)

def cache_set(key: str, value: Dict[str, Any]) -> None:
    # Store an AI response in the cache under the given key, loading the cache from disk if it has not been loaded yet, and saving the updated cache back to disk.
    global _cache
    if _cache is None:
        _cache = _load_cache()
    _cache[key] = value
    _save_cache(_cache)