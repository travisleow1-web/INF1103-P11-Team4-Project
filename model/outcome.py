from enum import Enum


class Outcome(str, Enum):
    """What should happen to a shipment once the rules have run."""
    PROCEED, DELAY, INSURE, ESCALATE, REJECT = "PROCEED", "DELAY", "INSURE", "ESCALATE", "REJECT"
