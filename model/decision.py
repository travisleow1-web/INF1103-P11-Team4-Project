import copy
from typing import Iterable, Optional
from .flag import Flag
from .outcome import Outcome
from .risk_level import RiskLevel


class Decision:
    """The verdict on one shipment. State is private; rules change it only through methods.

    Based on Jun Jie's Decision (Logic_ManagerPart2), with Outcome and Flag enums in place of text.
    """

    def __init__(self, shipment_id: str):
        self.__shipment_id = str(shipment_id)
        self.__risk = RiskLevel.LOW
        self.__outcome = Outcome.PROCEED
        self.__hold_shipment = False
        self.__needs_human = False
        self.__flags = []
        self.__actions = []
        self.__alerts = []
        self.__rationale = []

    @property
    def shipment_id(self) -> str:
        return self.__shipment_id

    @property
    def risk_level(self) -> RiskLevel:
        return self.__risk

    @property
    def overall_risk(self) -> str:
        """The risk as shown to users: 'Low', 'Medium', 'High' or 'Extreme'."""
        return self.__risk.label

    @property
    def outcome(self) -> Outcome:
        return self.__outcome

    @property
    def hold_shipment(self) -> bool:
        return self.__hold_shipment

    @property
    def needs_human(self) -> bool:
        return self.__needs_human

    @property
    def flags(self) -> tuple:
        return tuple(self.__flags)

    @property
    def actions(self) -> tuple:
        return tuple(self.__actions)

    @property
    def alerts(self) -> tuple:
        """Copies, so a caller cannot change the decision through them."""
        return tuple(copy.deepcopy(self.__alerts))

    @property
    def rationale(self) -> tuple:
        return tuple(self.__rationale)

    def has_flag(self, flag: Flag) -> bool:
        """True if a rule has already put this flag on the decision."""
        return flag in self.__flags

    def add_note(self, why: str, flag: Optional[Flag] = None, action: Optional[str] = None,
                 human: bool = False) -> None:
        """Record why a rule fired, plus an optional flag (no duplicates), action and human-review request."""
        if flag is not None:
            flag = Flag(flag)
            if flag not in self.__flags:
                self.__flags.append(flag)
        if action:
            self.__actions.append(action)
        if human:
            self.__needs_human = True
        self.__rationale.append(why)

    def add_action(self, action: str) -> None:
        """Add a step someone should take, such as 'Buy extra insurance'."""
        self.__actions.append(action)

    def raise_risk(self, level: RiskLevel) -> None:
        """Risk only ever goes up; a later rule cannot undo an earlier High."""
        level = RiskLevel(level)
        if level > self.__risk:
            self.__risk = level

    def hold(self) -> None:
        """Keep the shipment from leaving until someone releases it."""
        self.__hold_shipment = True

    def require_human(self) -> None:
        """Ask for a person to review this decision."""
        self.__needs_human = True

    def add_alert(self, recipient: str, channels: Iterable[str], message: str) -> None:
        """Note who should be told about this decision, and how."""
        self.__alerts.append({"recipient": recipient, "channels": list(channels), "message": message})

    def set_outcome(self, outcome: Outcome) -> None:
        """Set what should happen to the shipment. Unknown outcomes raise ValueError."""
        self.__outcome = Outcome(outcome)

    def to_dict(self) -> dict:
        """Plain dict for saving and display. Risk is its label, outcome and flags their values."""
        return {
            "shipment_id": self.__shipment_id,
            "overall_risk": self.overall_risk,
            "outcome": self.__outcome.value,
            "hold_shipment": self.__hold_shipment,
            "needs_human": self.__needs_human,
            "flags": [f.value for f in self.__flags],
            "actions": list(self.__actions),
            "alerts": copy.deepcopy(self.__alerts),
            "rationale": list(self.__rationale),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Decision":
        """Rebuild from to_dict() output. A missing key is a KeyError, a bad value a ValueError."""
        decision = cls(data["shipment_id"])
        decision.raise_risk(RiskLevel.parse(data["overall_risk"]))
        decision.set_outcome(Outcome(data["outcome"]))
        decision.__hold_shipment = bool(data["hold_shipment"])
        decision.__needs_human = bool(data["needs_human"])
        decision.__flags = [Flag(f) for f in data["flags"]]
        decision.__actions = [str(a) for a in data["actions"]]
        for alert in data["alerts"]:
            decision.add_alert(alert["recipient"], alert["channels"], alert["message"])
        decision.__rationale = [str(r) for r in data["rationale"]]
        return decision
