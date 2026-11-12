"""Dev-only driver: the real IO and Data layers with fake AI and Logic. Not part of the product.

    python -m tests.demo submit sample_data/shipments.csv
    python -m tests.demo search --risk HIGH --from 01/10/2026
"""
import argparse
import sys
from pathlib import Path
from data_layer.json_data_manager import JsonDataManager
from io_layer.csv_source import CsvSource
from io_layer.io_manager import IOManager
from model.port_registry import PortRegistry
from io_layer.shipment_validator import ShipmentValidator
from io_layer.source_error import SourceError
from main import assess_shipments
from tests.fakes import FakeAI, FakeLogic

DEMO_FILE = "demo_records.json"          # not shipments.json: the old DataManager uses another format there


def show(row, save_error=None):
    badge = "  [AI unavailable]" if row.get("ai_unavailable") else ""
    unsaved = f"  [not saved: {save_error}]" if save_error else ""
    print(f"{row['shipment_id']}  {row['origin']} -> {row['destination']}  "
          f"{row['departure']} to {row['arrival']}  risk={row['decision']['overall_risk']}  "
          f"outcome={row['decision']['outcome']}  human={row['decision']['needs_human']}{badge}{unsaved}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit", help="assess every shipment in a CSV file")
    submit.add_argument("csv")
    search = commands.add_parser("search", help="find saved records")
    for name in ("id", "origin", "destination", "from", "to", "risk", "outcome", "needs-human"):
        search.add_argument(f"--{name}", default="")
    args = parser.parse_args()

    ports = PortRegistry.from_json()
    data = JsonDataManager(DEMO_FILE, ports)
    io = IOManager(ShipmentValidator(ports), data, ports)

    if args.command == "submit":
        try:
            preview = io.preview(CsvSource(Path(args.csv).read_bytes()))
        except (SourceError, OSError) as error:
            sys.exit(f"Could not read the file: {error}")
        if preview.has_problems():
            for number, errors in preview.problems():
                print(f"row {number}: " + "; ".join(errors))
            sys.exit("Nothing was assessed. Fix the rows above and try again.")
        for record, save_error in assess_shipments(preview.valid_shipments(), FakeAI(), FakeLogic(), data):
            show(io.show_result(record), save_error)
    else:
        result = io.search({"shipment_id": args.id, "origin": args.origin, "destination": args.destination,
                            "departure_from": getattr(args, "from"), "departure_to": args.to,
                            "overall_risk": args.risk, "outcome": args.outcome,
                            "needs_human": args.needs_human})
        if result["kind"] == "results":
            for row in result["records"]:
                show(row)
        else:
            print(result["message"])


if __name__ == "__main__":
    main()
