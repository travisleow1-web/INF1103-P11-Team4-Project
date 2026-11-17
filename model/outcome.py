from enum import Enum


class Outcome(str, Enum):
    PROCEED = "PROCEED"
    DELAY = "DELAY"
    INSURE = "INSURE"
    ESCALATE = "ESCALATE"
    REJECT = "REJECT"
