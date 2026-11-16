from dataclasses import dataclass
from typing import Optional
from .fetch_stage import FetchStage


@dataclass(frozen=True)
class FetchEvent:
    """One status report about fetching an AI assessment for one shipment."""

    shipment_id: str
    stage: FetchStage
    attempt: Optional[int] = None           # RETRYING: the attempt that just failed
    max_attempts: Optional[int] = None      # RETRYING: how many attempts are allowed in total
    detail: Optional[str] = None            # RETRYING and FAILED: why it failed
