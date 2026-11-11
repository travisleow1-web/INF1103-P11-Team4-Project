# IO layer design (web UI version)

The code is in `io_layer/` (one class per file) with tests in `tests/`. This file records the decisions behind it. The full note with the class diagram is in the team Project notes (`io-manager-design-notes.md`).

## Responsibility

The IO manager is the only layer that talks to the user. It reads shipment input (typed rows and CSV), validates it, prepares what the pages display, and searches saved records.

It reads saved records from the Data manager through `find(criteria)`. It does NOT call the AI, apply business rules, or write to storage.

The web layer (FastAPI routes and templates) is a thin shell: it passes form fields into `IOManager` and renders the dicts that come back. No rules and no parsing in routes. Routes are plain functions, so they are not in the class diagram.

## Decisions

| Question | Decision |
|---|---|
| Who runs AI, then Logic, then Data? | `main.py`'s `assess_shipments` generator, called by the route. Not IO, and no pipeline class |
| Shipment ID | One column, generated: `SHP-001`, `SHP-002`, ... continuing from the highest saved `SHP-###`. Only valid rows use up a number. A `shipment_id` column in a CSV is ignored |
| Dates | `DD/MM/YYYY` only. Arrival must be after departure. Stored as real dates, never strings |
| Ports | Only the 50 ports in `ports_reference_4.json`. Code or full label accepted |
| Input | Typed rows (table with "Add row") and CSV upload. `preview(*sources)` accepts both together |
| Invalid rows | For now any error shows the full error list and nothing runs (all-or-nothing). CSVs are assumed clean. The "submit the valid rows" prompt is parked |
| Search filters | Shipment ID, origin, destination, departure date range (from/to, inclusive), overall risk, outcome, needs human. `route_id` removed |
| Who parses the search form? | `IOManager.search(fields)` takes the raw form dict and builds `SearchCriteria` |
| Results | Summary table, per-shipment details (risk factors, insights, decision with flags, actions, alerts, rationale), streamed one by one as each shipment finishes |
| AI failure | A badge ("AI unavailable") only on shipments where the AI did not run |
| Validation | One `ShipmentValidator` with private checks; collects every error in a row; returns a `ValidationResult`, never raises for bad input |
| Errors | Storage failures, bad dates and unknown ports come back as `{"kind": "error", ...}`; the user never sees a stack trace. `preview()` raises `SourceError` for an unreadable or empty CSV; the route shows it with `io.show_error(str(error))` |
| Empty search | `{"kind": "empty", ...}`; the page offers the new-shipment form (IDs are always generated, so nothing is pre-filled) |
| Search result | `{"kind": "results", "summary": [...], "records": [...]}`: the summary table rows plus one detail dict per record |

## Classes (one per file)

`IOManager`, `ShipmentSource` (ABC), `FormSource`, `CsvSource`, `SourceError`, `ShipmentValidator`, `ValidationResult`, `Preview`.

Placeholders for the shared model and the Data manager, to be replaced when the team agrees them: `Port`, `PortRegistry`, `Shipment`, `SearchCriteria`, `StorageError`.

## What the Data manager must provide

- `find(criteria)` returns a list of records, or raises `StorageError`.
- Each record has `.shipment`, `.assessment` (with `to_dict()` and `is_fallback()`) and `.decision` (with `to_dict()` holding `overall_risk`, `outcome`, `needs_human`, ...).
- Mongo filters on `overall_risk`, `outcome` and `needs_human` use the `decision.` prefix.
- Dates are stored as real dates: a `datetime` at midnight UTC in Mongo, an ISO `YYYY-MM-DD` string in JSON. A range search cannot work on `DD/MM/YYYY` strings.
- No filters returns everything, newest first.

## Web layer

| Route | What it does |
|---|---|
| `GET /` | `io.show_input_form()` fills the page: row table, CSV upload, search form |
| `POST /submit` | builds `FormSource` and/or `CsvSource`, calls `io.preview(...)`. If `has_problems()`: show the errors and run nothing. Otherwise stream one result per shipment from `assess_shipments` |
| `POST /search` | `io.search(form_dict)`, renders the `kind` it returns (`results`, `empty`, `error`) |

An HTML date input sends `YYYY-MM-DD`, which the validator rejects. Use a date picker set to `d/m/Y` or a text box with a `DD/MM/YYYY` placeholder.

## Parked

- "Submit the valid rows, or cancel and fix the file" prompt.
- Overall report of all shipments, and a per-shipment pop-up.
- Duplicate-shipment check, download buttons, batch size cap.

## Known limits

- `IOManager.preview` reads every saved record to find the highest ID. Fine for mock data; add a `max_id` call to the Data manager if it gets slow.
- IDs are assigned at preview time, so two tabs previewing before either submits would get the same numbers.
- `DataManager` also has write methods, so `IOManager` could call them by mistake. Convention only.
- Row numbers in error messages count the rows submitted in order (CSV rows first, then typed rows), not file lines.
- If storage fails during `preview`, numbering restarts at `SHP-001`.
- Dropdown values for `overall_risk` and `outcome` must match what the Data manager stores (for example `LOW` versus `Low`). Build the dropdowns from the Logic enums so they cannot drift.
- `PortRegistry.find` checks the port code only, so a label with a wrong name (`SGSIN - Nonsense, ZZ`) is accepted. Harmless because the form uses a dropdown.
