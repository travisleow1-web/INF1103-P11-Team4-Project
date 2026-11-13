"""Rules that put a shipment on hold for a specific reason (Rules 3, 4 and 5)."""

from datetime import timedelta

from logic.businessrule import BusinessRule
from logic.decision import RiskLevel


class InsuranceRule(BusinessRule):
    """Rule 4: piracy_threat / severe_civil_unrest -> hold until extended insurance is confirmed."""

    TRIGGERS = frozenset({"piracy_threat", "severe_civil_unrest"})

    def apply(self, record, decision, now):
        present = {f["type"] for f in record["risk_factors"]} | {record["primary_risk_factor"]}
        triggered = self.TRIGGERS & present
        if triggered:
            decision.hold()
            decision.raise_risk(RiskLevel.HIGH)
            decision.add_note(f"Rule 4: {', '.join(sorted(triggered))} detected, holding until insurance "
                              "confirmed", "Premium Increase Required",
                              "Update financial profile: extended insurance needed", human=True)


class RouteHistoryRule(BusinessRule):
    """Rule 3: a 'Low' route flagged or delayed recently needs dispatcher sign-off."""

    def __init__(self, config, history_source):
        self._config = config
        self._history = history_source  # association: used, not owned

    def apply(self, record, decision, now):
        if decision.risk_level != RiskLevel.LOW:
            return  # only double-checks shipments that are still Low
        window = self._config.history_window_days
        try:
            past = self._history.get_route_history(record["route_id"], now - timedelta(days=window))
        except (KeyError, TypeError, ValueError) as exc:
            decision.add_note(f"Rule 3: could not read route history ({exc}), needs human",
                              "Route history unavailable", human=True)
            return
        problems = [p for p in past if p.get("flagged") or p.get("delayed")]
        if not problems:
            decision.add_note(f"Rule 3: Low risk and clean {window}-day history, auto-approve")
            return
        decision.hold()
        decision.add_note(f"Rule 3: AI says Low but {len(problems)} shipment(s) on route {record['route_id']} "
                          f"were flagged or delayed in the last {window} days", "Cautionary Override",
                          "Require human dispatcher sign-off", human=True)


class ProcurementRule(BusinessRule):
    """Rule 5 (multi-condition): Cargo Destruction predicted AT the origin port -> reorder the goods."""

    DESTRUCTION_IMPACTS = frozenset({"Cargo Destruction"})

    def apply(self, record, decision, now):
        destroyed = record["expected_impact"] in self.DESTRUCTION_IMPACTS
        at_origin = record["affected_location"] == record["origin_port"]
        if destroyed and at_origin:
            decision.hold()
            decision.add_alert("procurement_team", ["email"],
                               f"Shipment {record['shipment_id']} is at risk of destruction at "
                               f"{record['origin']}. Consider reordering to avoid stock-out.")
            decision.add_note(f"Rule 5: Cargo Destruction @{record['origin_port']} (origin)", "Procurement Alert",
                              "Reorder goods immediately: the goods on this shipment")
