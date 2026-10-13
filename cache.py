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
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Failed to load AI response cache from %s: %s", CACHE_FILE, exc)
        return {}

def _save_cache(cache_data: Dict[str, Any]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, default=str)
    except Exception as exc:
        log.warning("Failed to save AI response to %s: %s", CACHE_FILE, exc)

def get_cache_key(shipment: Dict[str, Any]) -> str:
    today = datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()
    fields = {k: v for k, v in shipment.items() if k != "shipment_id"}
    payload = json.dumps(fields, sort_keys=True, default=str) + f"|{today}|v{SCHEMA_VERSION}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def cache_get(key: str) -> Optional[Dict[str, Any]]:
    global _cache
    if _cache is None:
        _cache = _load_cache()
    return _cache.get(key)

def cache_set(key: str, value: Dict[str, Any]) -> None:
    global _cache
    if _cache is None:
        _cache = _load_cache()
    _cache[key] = value
    _save_cache(_cache)