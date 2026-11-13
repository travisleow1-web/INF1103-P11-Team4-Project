"""OutcomeResolver: turns flags and risk into one final outcome."""

from logic.decision import RiskLevel


class OutcomeResolver:
    """Turns the accumulated flags and risk into one outcome, then applies the human-review gate."""

    def resolve(self, decision):
        if decision.has_flag("Procurement Alert"):
            decision.set_outcome("DELAY")
        elif decision.has_flag("Premium Increase Required"):
            decision.set_outcome("INSURE")
        elif decision.risk_level == RiskLevel.HIGH:
            decision.set_outcome("DELAY")
            decision.add_action("Delay departure until conditions clear")
            decision.require_human()
        else:
            decision.set_outcome("PROCEED")
            if decision.risk_level == RiskLevel.MEDIUM:
                decision.add_action("Proceed with monitoring")
        if decision.hold_shipment and decision.outcome == "PROCEED":
            decision.set_outcome("ESCALATE")
        # Final gate: anything needing a human is never fully automatic
        if decision.needs_human:
            if decision.outcome == "PROCEED":
                decision.set_outcome("ESCALATE")
            decision.add_action("Route to human review queue")
