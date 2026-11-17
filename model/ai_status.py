from enum import Enum


class AIStatus(str, Enum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    FALLBACK = "FALLBACK"
