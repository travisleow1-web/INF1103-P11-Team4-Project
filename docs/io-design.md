# IO layer design (web UI version)

The code is in `io_layer/` (one class per file) with tests in `tests/`. This file records the decisions behind it as built. The full note with the class diagram is in the team Project notes (`io-manager-design-notes.md`).

## Responsibility

The IO manager is the only layer that talks to the user. It reads shipment input (typed rows and CSV), validates it, numbers the shipments, prepares what the pages display, and searches saved records.

It reads saved records from the Data manager through `find(criteria)`. It does NOT call the AI, apply business rules, or write to storage.

The web layer (`web/app.py`, FastAPI routes and Jinja templates) is a thin shell: it passes form fields into `IOManager` and renders the dicts that come back. No rules and no parsing in routes. Routes are plain functions, so they are not in the class diagram.

## Decisions

| Question | Decision |
|---|---|
| Who runs AI, then Logic, then Data? | `main.assess_shipments`, a generator that yields `(record, save_error)` per shipment. `main.create_app` passes it into `create_web_app(..., run=assess_shipments)`, so `web/` never imports `main`. No pipeline class |
| Shipment ID | Generated: `SHP-001`, `SHP-002`, ... continuing from the highest saved `SHP-###` or the highest already handed out to a running submission, whichever is larger (under a lock, so overlapping submissions never share an ID). Only valid rows in a preview without problems use up a number. A `shipment_id` column in a CSV is ignored |
| Saved records cannot be read | `preview()` raises `StorageError("Cannot assign shipment IDs: saved records could not be read.")` instead of restarting at `SHP-001`; the submit page shows it and runs nothing, so no ID is handed out twice |
| Dates | `DD/MM/YYYY` only. Arrival must be after departure. Stored as real dates, never strings. Times are shown as `DD/MM/YYYY HH:MM SGT` |
| Ports | Only the 50 ports in `ports_reference_4.json`. Code or full label accepted |
| Input | Typed rows (table with "Add row") and CSV upload, together. `preview(*sources)` reads CSV rows first, then typed rows. `FormSource.many(fields)` makes one source per non-blank typed row |
| Invalid rows | All-or-nothing: any error shows every row's errors and nothing runs. The validator checks every field that is present even when another is missing, and uses plain names ("Destination port is missing", "Origin: unknown port 'X'"). Typed rows with errors are highlighted and their inputs point at the row's errors (`aria-invalid`, `aria-describedby`) |
| Search filters | Shipment ID, origin, destination, departure date range (from/to, inclusive), overall risk, outcome, needs human. Risk and outcome must be one of the dropdown values (`show_input_form()` builds them from `RiskLevel` and `Outcome`) |
| Who parses the search form? | `IOManager.search(fields)` takes the raw query fields and builds `SearchCriteria` |
| Results | Summary table plus a `<details>` row per shipment (risk factors, insights, decision with flags, actions, alerts, rationale), streamed one row at a time as each shipment finishes |
| AI failure | An "AI unavailable" badge only on FALLBACK assessments |
| Validation | One `ShipmentValidator` with private checks; returns a `ValidationResult`, never raises for bad input |

## Error handling as built

| Problem | What the user sees |
|---|---|
| Invalid rows | HTTP 422, every row's errors, typed rows kept and highlighted |
| CSV missing columns | "The file is missing the columns: ..." (HTTP 400) |
| CSV not UTF-8 text | "This file is not a readable CSV (UTF-8 text)." (HTTP 400) |
| CSV with a header only, or nothing entered | "The file has no shipments." / "Add at least one shipment or choose a CSV file." (HTTP 400) |
| Upload over 1 MB | "The CSV file is larger than 1 MB." (HTTP 413), refused from `Content-Length` before the form is read |
| Saved records unreadable at submit | "Cannot assign shipment IDs: saved records could not be read. Nothing was assessed." (HTTP 503) |
| Database unreachable at startup | A red banner on every page: "Database unavailable. Results will not be saved." The driver detail goes to the log only |
| A save fails during a run | That row says "Not saved" with the short reason; the other shipments still run |
| One damaged saved record | Skipped and logged by the Data manager; the rest are still listed |
| Bad search input | `{"kind": "error", "message": ...}` with every problem (unknown port, bad date, from after to, risk or outcome not offered) |
| Unexpected error mid-stream | The table ends with "Assessment stopped after n of N shipments ..." and the page still closes |

## Classes (one per file)

`IOManager`, `ShipmentSource` (ABC), `FormSource`, `CsvSource`, `SourceError`, `ShipmentValidator`, `ValidationResult`, `Preview`.

The shared model (`Port`, `PortRegistry`, `Shipment`, `ShipmentRecord`, `SearchCriteria`, `StorageError`, `AIAssessment`, `Decision` and the enums) lives in `model/`.

## What IO needs from the Data manager

- `find(criteria)` returns a list of `ShipmentRecord`, newest first, or raises `StorageError`. No filters returns everything.
- Each record has `.shipment`, `.assessment` (with `to_dict()`, `is_fallback()` and `fetched_at`), `.decision` (with `to_dict()`) and `.saved_at`.
- Mongo filters on `overall_risk`, `outcome` and `needs_human` use the `decision.` prefix; risk and outcome ignore case.
- Dates are stored as real dates: a `datetime` at midnight UTC in Mongo, an ISO `YYYY-MM-DD` string in JSON.

## Web layer

| Route | What it does |
|---|---|
| `GET /` | `io.show_input_form()` fills the page: row table, CSV upload, link to search. Says up front when the AI or Logic is not connected (without a Gemini key: "AI is not connected: set GEMINI_API_KEY in .env (or start with DEMO_MODE=1).") |
| `POST /submit` | Builds `CsvSource` and `FormSource.many(...)`, calls `io.preview(...)`. Problems: show them and run nothing. AI or Logic not connected: "N shipments are valid." plus which one is missing Otherwise streams one result row per shipment from the runner |
| `GET /search` | `io.search(query fields)`, rendered by `kind`: `results`, `empty` (with a link to the input page) or `error` |

On phones (below 640px) typed rows stack one field per line and result rows become cards, so nothing scrolls sideways.

## Parked

- "Submit the valid rows, or cancel and fix the file" prompt.
- Overall report of all shipments, and a per-shipment pop-up.
- Duplicate-shipment check, download buttons, batch size cap.

## Known limits

- `IOManager.preview` reads every saved record to find the highest ID. Fine for coursework data; add a `max_id` call to the Data manager if it gets slow.
- IDs are assigned at preview time, so two tabs previewing before either submits would get the same numbers; the second save of an ID fails with "already saved" and that row shows "Not saved".
- A damaged saved record is skipped, so its ID could be handed out again; the save then fails as a duplicate.
- `DataManager` also has write methods, so `IOManager` could call them by mistake. Convention only.
- `PortRegistry.find` checks the port code only, so a label with a wrong name (`SGSIN - Nonsense, ZZ`) is accepted. Harmless because the form suggests the real labels.
