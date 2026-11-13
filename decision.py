"""RiskLevel and Decision: risk levels and the Logic Manager's verdict on one shipment."""

from enum import IntEnum


class RiskLevel(IntEnum):
    """Ordered risk levels, so they can be compared (LOW < MEDIUM < HIGH)."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def from_text(cls, text):
        """'Medium' / 'medium' / 'MEDIUM' -> RiskLevel.MEDIUM. Unknown text counts as LOW."""
        return cls.__members__.get(str(text).strip().upper(), cls.LOW)

    @property
    def label(self):
        """Display form used in decisions: 'Low' / 'Medium' / 'High'."""
        return self.name.capitalize()


class Decision:
    """The verdict on one shipment. State is private; rules change it only through methods."""

    OUTCOMES = ("PROCEED", "DELAY", "INSURE", "ESCALATE", "REJECT")

    def __init__(self, shipment_id):
        self._shipment_id = str(shipment_id)
        self._risk = RiskLevel.LOW
        self._outcome = "PROCEED"
        self._hold_shipment = False
        self._needs_human = False
        self._flags = []
        self._actions = []
        self._alerts = []
        self._rationale = []

    @property
    def shipment_id(self):
        return self._shipment_id

    @property
    def risk_level(self):
        return self._risk

    @property
    def overall_risk(self):
        return self._risk.label

    @property
    def outcome(self):
        return self._outcome

    @property
    def hold_shipment(self):
        return self._hold_shipment

    @property
    def needs_human(self):
        return self._needs_human

    @property
    def flags(self):
        return tuple(self._flags)

    @property
    def actions(self):
        return tuple(self._actions)

    @property
    def alerts(self):
        return tuple(dict(a) for a in self._alerts)

    @property
    def rationale(self):
        return tuple(self._rationale)

    def has_flag(self, flag):
        return flag in self._flags

    def add_note(self, why, flag=None, action=None, human=False):
        """Record why a rule fired, plus an optional flag (no duplicates), action and human-review request."""
        if human:
            self._needs_human = True
        if flag and flag not in self._flags:
            self._flags.append(flag)
        if action:
            self._actions.append(action)
        self._rationale.append(why)

    def add_action(self, action):
        self._actions.append(action)

    def raise_risk(self, level):
        """Risk only ever goes up; a later rule cannot undo an earlier High."""
        if level > self._risk:
            self._risk = level

    def hold(self):
        self._hold_shipment = True

    def require_human(self):
        self._needs_human = True

    def add_alert(self, recipient, channels, message):
        self._alerts.append({"recipient": recipient, "channels": list(channels), "message": message})

    def set_outcome(self, outcome):
        if outcome not in self.OUTCOMES:
            raise ValueError(f"Unknown outcome {outcome!r}")
        self._outcome = outcome

    def to_dict(self):
        """Plain dict for the Data Manager (saving) and IO Manager (display)."""
        return {"shipment_id": self._shipment_id, "overall_risk": self.overall_risk,
                "outcome": self._outcome, "hold_shipment": self._hold_shipment,
                "needs_human": self._needs_human, "flags": list(self._flags),
                "actions": list(self._actions), "alerts": [dict(a) for a in self._alerts],
                "rationale": list(self._rationale)}
