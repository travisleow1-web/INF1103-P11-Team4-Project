import pandas as pd
import questionary
import ai_manager
import data_manager
import logic_manager
import validator


def ask_port(message, validate=validator.validate_port):
    """Prompt for a port with autocomplete and return its upper-cased code (the part before " - ")."""
    answer = questionary.autocomplete(
        message,
        choices=validator.PORT_CHOICES,
        match_middle=True,
        validate=validate,
    ).unsafe_ask()
    return answer.split(" - ")[0].strip().upper()

def origin_port():
    """Prompt for the origin port and return its code."""
    return ask_port("Origin port:")

def destination_port(origin):
    """Prompt for the destination port code; the origin port is rejected."""
    return ask_port(
        "Destination port:",
        validate=lambda answer: validator.validate_destination_port(answer, origin),
    )

def departure_time():
    """Prompt for the departure date (DD/MM/YYYY) and return it as a string."""
    answer = questionary.text(
        "Departure time (DD/MM/YYYY):", validate=validator.validate_date
    ).unsafe_ask()
    return answer.strip()

def arrival_time(departure):
    """Prompt for the arrival date (DD/MM/YYYY), which must be after the departure, and return it as a string."""
    answer = questionary.text(
        "Arrival time (DD/MM/YYYY):",
        validate=lambda answer: validator.validate_arrival_date(answer, departure),
    ).unsafe_ask()
    return answer.strip()

def manual_shipments():
    """Ask for one or more shipments and return them as a DataFrame.

    IDs are assigned later by input_method; ai_manager fills in the port coordinates.
    """
    rows = []
    while True:
        origin = origin_port()
        destination = destination_port(origin)
        departure = departure_time()
        rows.append(
            {
                "origin_port": origin,
                "destination_port": destination,
                "departure_time": departure,
                "arrival_time": arrival_time(departure),
            }
        )
        if not questionary.confirm("Add another shipment?").unsafe_ask():
            break
    return pd.DataFrame(rows)

def assign_shipment_ids(df):
    """Return df with shipment_id first (SHP-001, SHP-002, ...), replacing any existing IDs."""
    df = df.drop(columns="shipment_id", errors="ignore")
    df.insert(0, "shipment_id", [f"SHP-{i:03d}" for i in range(1, len(df) + 1)])
    return df

def input_method():
    """Ask whether to enter shipments manually or from a CSV file; return them with IDs assigned (None on Back)."""
    selection = questionary.select(
        "How do you want to add shipments?",
        choices=["Enter manually", "Upload a CSV file", "Back"],
        erase_when_done=True,
    ).unsafe_ask()
    if selection == "Back":
        return None
    if selection == "Upload a CSV file":
        return assign_shipment_ids(csv_shipments())
    return assign_shipment_ids(manual_shipments())

def csv_shipments():
    """Load shipments from a CSV file, then optionally append manual ones.

    An unreadable file shows the error and asks for the path again.
    """
    while True:
        path = questionary.path("CSV file path:", validate=validator.validate_csv_path).unsafe_ask()
        try:
            # Read everything as text, with blank cells as "" instead of NaN.
            df = pd.read_csv(path.strip(), dtype=str, keep_default_na=False)
        except (
            pd.errors.ParserError,
            pd.errors.EmptyDataError,
            UnicodeDecodeError,
        ) as e:
            print(f"Could not read file: {e}")
            continue
        print(df)
        break

    if questionary.confirm("Add further shipments manually?").unsafe_ask():
        return pd.concat([df, manual_shipments()], ignore_index=True)
    return df

def show_summary(assessments):
    """Print one row per shipment with its scalar fields.

    primary_severity is "-" if the AI listed no factor matching primary_risk_factor.
    """
    rows = [
        {
            "shipment_id": a["shipment_id"],
            "expected_impact": a["expected_impact"],
            "confidence_score": a["confidence_score"],
            "primary_factor": a["primary_risk_factor"],
            "primary_severity": next(
                (f["severity"] for f in a["risk_factors"] if f["type"] == a["primary_risk_factor"]), "-"
            ),
            "n_risk_factors": len(a["risk_factors"]),
            "conflicting_sources": a["conflicting_sources"],
        }
        for a in assessments.to_dict("records")
    ]
    print(pd.DataFrame(rows).to_string(index=False))

def show_details(assessments):
    """Print a text block per shipment: header, each risk factor, then the insights."""
    for a in assessments.to_dict("records"):
        print(
            f"\n{a['shipment_id']} | impact: {a['expected_impact']}"
            f" | confidence: {a['confidence_score']}"
        )
        for f in a["risk_factors"]:
            print(f"    [{f['severity']}] {f['type']}: {f['detail']}")
        print("  Insights:")
        for insight in a["insights"]:
            print(f"    - {insight}")

def show_decisions(results):
    """Print the Logic Manager's decision for each (record, decision) pair."""
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

def get_search_criteria(db_records):
    risk = ""
    outcome = ""
    needs_human = ""
    Add_Criteria = questionary.select(
        "Would you like to add a filter",
        choices=["Yes","No (Run Search)","Back"],
        erase_when_done=True,
    ).unsafe_ask()
    if Add_Criteria == "Back":
        return
    match Add_Criteria:
        case "Yes":
            while True:
                print("Current Filters")
                print(f"Risk : {risk}")
                print(f"Outcome : {outcome}")
                print(f"Needs Human : {needs_human}")

                Criteria = questionary.select(
                    "Filters",
                    choices=["Risk","Outcome","Needs Human","Back (Finished Adding Filter)"],
                    erase_when_done=True,
                ).unsafe_ask()
                match Criteria:
                    case "Risk":
                        risk = questionary.select(
                            "Risk",
                            choices=["Low", "Medium", "High"],
                            erase_when_done=True,
                        ).unsafe_ask()
                    case "Outcome":
                        outcome = questionary.select(
                            "Outcome",
                            choices=["DELAY","INSURE","PROCEED","ESCALATE","REJECT"],
                            erase_when_done=True,
                        ).unsafe_ask()
                    case "Needs Human":
                        needs_human = questionary.select(
                            "Needs Human",
                            choices=["YES","NO"],
                            erase_when_done=True,
                        ).unsafe_ask()
                    case "Back (Finished Adding Filter)":
                        break
    if needs_human == "YES":
        needs_human = True
    elif needs_human == "NO":
        needs_human = False
    search_filter = {
        "risk" : risk,
        "outcome" : outcome,
        "needs_human" : needs_human,
    }
    results = data_manager.query_records(db_records, search_filter)
    show_decisions([(record, record["decision"]) for record in results])

def main_menu(db_records):
    """Show the main menu and run the chosen action. Returns False when the user quits, otherwise True."""
    selection = questionary.select(
        "Main Menu",
        choices=["Add Shipment", "Search by Criteria", "Quit"],
        erase_when_done=True,
    ).ask()
    try:
        match selection:
            case "Add Shipment":
                shipments = input_method()
                if shipments is None:  # the user chose Back
                    return True
                assessments = ai_manager.assess_shipments(shipments)
                results = logic_manager.evaluate_shipments(assessments, db_records)
                data_manager.add_record(data_manager.DB_FILE, db_records, results)
                show_summary(assessments)
                show_details(assessments)
                show_decisions(results)
            case "Search by Criteria":
                get_search_criteria(db_records)
            case "Quit" | None:  # None: the user pressed Ctrl+C at the prompt
                return False
    except KeyboardInterrupt:  # Ctrl+C inside an action: back to the menu
        print("Cancelled, back to the main menu.")
    return True

if __name__ == "__main__":
    # Past records are loaded once so Rule 3 can check the last 21 days.
    db_records = data_manager.load_records(data_manager.DB_FILE)
    while main_menu(db_records):
        pass
