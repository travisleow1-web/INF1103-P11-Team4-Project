from model.decision import Decision
from model.flag import Flag
from model.outcome import Outcome
from model.risk_level import RiskLevel


class OutcomeResolver:
    """Turns the accumulated flags and risk into one outcome, then applies the human-review gate.

    Based on Jun Jie's OutcomeResolver (Logic_ManagerPart2), with Extreme risk leading to REJECT.
    """

    def resolve(self, decision: Decision) -> None:
        """Set the decision's outcome. Runs once, after every rule."""
        if decision.risk_level >= RiskLevel.EXTREME:
            decision.set_outcome(Outcome.REJECT)
        elif decision.has_flag(Flag.PROCUREMENT_ALERT):
            decision.set_outcome(Outcome.DELAY)
        elif decision.has_flag(Flag.PREMIUM_INCREASE):
            decision.set_outcome(Outcome.INSURE)
        elif decision.risk_level >= RiskLevel.HIGH:
            decision.set_outcome(Outcome.DELAY)
            decision.add_action("Delay departure until conditions clear")
            decision.require_human()
        else:
            decision.set_outcome(Outcome.PROCEED)
            if decision.risk_level >= RiskLevel.MEDIUM:
                decision.add_action("Proceed with monitoring")
        if decision.hold_shipment and decision.outcome is Outcome.PROCEED:
            decision.set_outcome(Outcome.ESCALATE)
        # Final gate: anything needing a human is never fully automatic
        if decision.needs_human:
            if decision.outcome is Outcome.PROCEED:
                decision.set_outcome(Outcome.ESCALATE)
            decision.add_action("Route to human review queue")
