from enum import Enum


class Outcome(str, Enum):
    """What should happen to a shipment once the rules have run."""

    PROCEED = "PROCEED"
    DELAY = "DELAY"
    INSURE = "INSURE"
    ESCALATE = "ESCALATE"
    REJECT = "REJECT"
