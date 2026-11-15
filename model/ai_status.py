from enum import Enum


class AIStatus(str, Enum):
    """Where an assessment came from: a live AI call, the cache, or the fallback when the AI failed."""
    LIVE, CACHED, FALLBACK = "LIVE", "CACHED", "FALLBACK"
