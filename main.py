import ai_manager
import data_manager
import io_manager
import logic_manager

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
    io_manager.show_decisions(results)


if __name__ == "__main__":
    main()