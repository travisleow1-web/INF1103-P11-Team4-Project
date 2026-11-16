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

    __MESSAGES = {
        FetchStage.CACHE_HIT: "using saved assessment (cache)",
        FetchStage.STARTED: "fetching in progress...",
        FetchStage.RETRYING: "attempt {attempt}/{max_attempts} failed ({detail}), trying again...",
        FetchStage.SUCCEEDED: "fetching complete",
        FetchStage.FAILED: "fetching failed ({detail}), using fallback assessment",
    }

    def describe(self) -> str:
        """The event in words, for example 'fetching in progress...'. Used by the console and the web page."""
        return self.__MESSAGES[self.stage].format(
            attempt=self.attempt, max_attempts=self.max_attempts, detail=self.detail or "no details")
