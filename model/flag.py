from enum import Enum


class Flag(str, Enum):
    """Flags a rule can put on a decision. The values are the wording shown to users."""

    PERFECT_STORM = "Perfect Storm"
    SIGNIFICANT_DELAY = "Significant Delay Expected"
    COMPOUND_RISK = "Compound Risk"
    AI_FLAGGED = "AI flagged for review"
    PREMIUM_INCREASE = "Premium Increase Required"
    CAUTIONARY_OVERRIDE = "Cautionary Override"
    ROUTE_HISTORY_UNAVAILABLE = "Route history unavailable"
    PROCUREMENT_ALERT = "Procurement Alert"
    LOW_CONFIDENCE = "Low AI confidence"
    OUTDATED_DATA = "Outdated external data"
    CONFLICTING_SOURCES = "Conflicting sources"
    AI_UNAVAILABLE = "AI unavailable"
    UNREGISTERED_LOCATION = "Unregistered location"
    RULE_ERROR = "Rule error"
