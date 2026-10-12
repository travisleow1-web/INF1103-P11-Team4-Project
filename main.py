import ai_manager
import data_manager
import io_manager
import logic_manager


def show_decisions(results):
    """Print the Logic Manager's decision for each shipment.

    results is the list of (record, decision) pairs from
    logic_manager.evaluate_shipments().
    """
    print("\n========== DECISIONS ==========")
    for record, d in results:
        print(f"\n{d['shipment_id']} | {record.get('origin', '?')} -> {record.get('destination', '?')}")
        print(f"  Outcome     : {d['outcome']}")
        print(f"  Overall risk: {d['overall_risk']}")
        hold = " (shipment on hold)" if d['hold_shipment'] else ""
        print(f"  Human review: {'YES' if d['needs_human'] else 'no'}{hold}")
        if d['flags']:
            print(f"  Flags       : {', '.join(d['flags'])}")
        for action in d['actions']:
            print(f"    * {action}")
        for alert in d['alerts']:
            print(f"    ! Alert to {alert['recipient']} via {'/'.join(alert['channels'])}")
        if d['rationale']:
            print("  Why:")
            for reason in d['rationale']:
                print(f"    - {reason}")


def main():
    """Run the full pipeline.

    IO Manager (input) -> AI Manager (risk assessment) -> Logic Manager
    (business rules) -> Data Manager (save) -> display.
    """
    shipments = io_manager.input_method()
    assessments = ai_manager.assess_shipments(shipments)

    # Past records are loaded first so Rule 3 can check the last 21 days.
    db_records = data_manager.load_records(data_manager.DB_FILE)
    results = logic_manager.evaluate_shipments(assessments, db_records)

    for record, decision in results:
        try:
            data_manager.add_record(
                data_manager.DB_FILE, db_records, record,
                logic_manager.decision_to_dict(decision),
            )
        except (OSError, TypeError) as exc:
            print(f"Warning: could not save {decision['shipment_id']}: {exc}")

    io_manager.show_summary(assessments)
    io_manager.show_details(assessments)
    show_decisions(results)


if __name__ == "__main__":
    main()