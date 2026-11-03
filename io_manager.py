import pandas as pd
import questionary
import ai_manager
import data_manager
import logic_manager
import validator
from mongodb import MongoDataManager


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

def mongo_search(Mongo_DM):
    """Find Shipment Record via a filter"""

    # Returns a Python list of selected strings, e.g. ['origin_port', 'departure_time']
    chosen_filters = questionary.checkbox(
    "Select fields to modify (Space to select, Enter to finish):",
    choices=[
        questionary.Choice(title="Shipment ID", value="shipment_id"),
        questionary.Choice(title="Route ID", value="route_id"),
        questionary.Choice(title="Origin", value="origin"),
        questionary.Choice(title="Overall Risk", value="overall_risk"),
        questionary.Choice(title="Outcome", value="outcome"),
        questionary.Choice(title="Needs Human", value="needs_human"),
    ]).ask()

    field_labels = {
    "shipment_id": "Shipment ID",
    "route_id": "Route ID",
    "origin": "Origin",
    "overall_risk": "Overall Risk",
    "outcome": "Outcome",
    "needs_human": "Needs Human",
}

    filter_values = {}


    for filter in chosen_filters:
        label = field_labels.get(filter)
        if filter == "needs_human":
            filter_values[filter] = questionary.confirm("Needs Human: ", default=False).ask()

        # Predefined dropdown choice for risk levels
        elif filter == "overall_risk":
             filter_values[filter] = questionary.select(
            "Overall Risk: ",
            choices=["Low", "Medium", "High"]
        ).ask()
        else:
            filter_values[filter] = questionary.text(f"Enter {label}: ").ask()
    
    results = Mongo_DM.FindRecord(filter_values)
    show_decisions([(record, record["decision"]) for record in results])
    

def main_menu(Mongo_DM):
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
                results = logic_manager.evaluate_shipments(assessments, Mongo_DM)
                Mongo_DM.InsertRecord(results)
                show_summary(assessments)
                show_details(assessments)
                show_decisions(results)
            case "Search by Criteria":
                mongo_search(Mongo_DM)
            case "Quit" | None:  # None: the user pressed Ctrl+C at the prompt
                return False
    except KeyboardInterrupt:  # Ctrl+C inside an action: back to the menu
        print("Cancelled, back to the main menu.")
    return True

if __name__ == "__main__":
    # Past records are loaded once so Rule 3 can check the last 21 days.
    #Data_Manager = data_manager.DataManager()
    Mongo_DM = MongoDataManager()
    while main_menu(Mongo_DM):
        pass
