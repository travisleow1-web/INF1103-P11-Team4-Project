from enum import Enum


class RiskType(str, Enum):
    """The kinds of risk the AI may report. NONE means no risk was found."""

    WEATHER = "weather"
    SEVERE_CROSSWINDS = "severe_crosswinds"
    PORT_CONGESTION = "port_congestion"
    LABOR_SHORTAGE = "labor_shortage"
    PIRACY_THREAT = "piracy_threat"
    SEVERE_CIVIL_UNREST = "severe_civil_unrest"
    GEOPOLITICAL = "geopolitical"
    INFRASTRUCTURE_DISRUPTION = "infrastructure_disruption"
    NONE = "none"
