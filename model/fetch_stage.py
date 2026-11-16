from enum import Enum


class FetchStage(str, Enum):
    """Where one AI fetch has got to. The AI manager reports these; it never prints them."""

    CACHE_HIT = "CACHE_HIT"     # a saved reply was used, no model call needed
    STARTED = "STARTED"         # fetching has begun
    RETRYING = "RETRYING"       # an attempt failed and another will follow
    SUCCEEDED = "SUCCEEDED"     # the model replied and the reply was valid
    FAILED = "FAILED"           # no usable reply, the fallback assessment is used
