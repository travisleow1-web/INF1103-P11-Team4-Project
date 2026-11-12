# Handoff guide for teammates

How the Phase 2 app is put together, and where your part plugs in.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env
DEMO_MODE=1 uvicorn main:create_app --factory --reload
```

Open http://127.0.0.1:8000, upload `sample_data/shipments.csv`, then try **Search**.

## Demo mode

`DEMO_MODE=1` makes `create_app()` use `FakeAI` and `FakeLogic` from `tests/fakes.py` instead of the real managers, and every page shows a yellow banner "Demo mode: fake AI and rules". The fakes give each shipment a low, medium or high weather risk based on its number. They live under `tests/` and never run unless demo mode is on.

Without demo mode, the AI and Logic come from `build_ai()` and `build_logic()` in `main.py`. While those return `None`, the submit page validates the rows and then says "N shipments are valid. AI and Logic are not connected yet."

## Folder map

| Folder or file | What is in it |
|---|---|
| `model/` | The shared model, one class per file: `Port`, `PortRegistry`, `Shipment`, `RiskFactor`, `Insight`, `AIAssessment`, `Decision`, `ShipmentRecord`, `SearchCriteria`, `StorageError`, and the enums `RiskLevel`, `RiskType`, `Outcome`, `AIStatus`, `Flag` |
| `io_layer/` | `IOManager` (validation, ID numbering, search, display dicts), `FormSource` and `CsvSource`, `ShipmentValidator`, `Preview`, `ValidationResult`, `SourceError`. Design notes: `docs/io-design.md` |
| `data_layer/` | `DataManager` (ABC) with `JsonDataManager` (default), `MongoDataManager` and `UnavailableDataManager`; `RecordSerializer` |
| `ai_layer/` | AI manager (PR 2) |
| `logic_layer/` | Logic manager and rules (PR 3) |
| `web/app.py` | `create_web_app(...)`: the FastAPI routes `GET /`, `POST /submit`, `GET /search` |
| `web/templates/` | Jinja templates. `_header.html` and `_footer.html` wrap every page; `_macros.html` holds the badges and the details row |
| `web/static/` | `style.css` and `add_row.js` (the only JavaScript) |
| `main.py` | Composition root: `assess_shipments`, `build_data`, `build_ai`, `build_logic`, `create_app` |
| `tests/` | pytest tests, `helpers.py` (shared test data) and `fakes.py` (FakeAI, FakeLogic) |

The flow for one submission: the route calls `io.preview(...)`. If every row is valid, `main.assess_shipments` runs, for each shipment, `ai.assess` then `logic.evaluate` then `data.save`, and yields `(record, save_error)`. The route streams one table row per shipment. The managers never call each other; only `main.py` knows all of them.

## Connect your layer

- **AI (PR 2):** fill in `build_ai()` in `main.py`. Put the `ai_layer` imports inside that function. Return `None` when `GEMINI_API_KEY` is not set. `assess(shipment)` must return an `AIAssessment`; on failure return `AIAssessment.fallback()`, which the pages mark "AI unavailable".
- **Logic (PR 3):** fill in `build_logic(data, ports)` the same way. `evaluate(shipment, assessment, now)` returns a `Decision`. Route history comes from `data.find_route_history(route_id, since)`.

Each PR edits only its own function in `main.py`, so the two do not conflict.

## How to add a page

1. Add a template in `web/templates/` that starts with `{% set title = "..." %}{% include "_header.html" %}` and ends with `{% include "_footer.html" %}`.
2. Add a route inside `create_web_app` in `web/app.py` that collects the raw fields, calls one `IOManager` method and returns `page(request, "your_page.html", ...)`. Keep parsing and rules out of the route.
3. If the page needs new display data, add a `show_...` method to `IOManager` that returns a plain dict.
4. Link it from the navigation in `_header.html`, label every input, and add a test in `tests/test_web.py`.

Jinja autoescape is on. Never use `|safe` on data, and show risk and outcome as text, not only as colour.

## How to add a rule (Logic layer)

1. Add a `Rule` subclass in its own file in `logic_layer/` and implement `apply(...)`.
2. Change the decision only through its methods: `raise_risk`, `add_note(why, flag, action, human)`, `set_outcome`, `hold`, `require_human`, `add_alert`. Risk only goes up.
3. Use a `Flag` member for any flag. A new flag needs a new member in `model/flag.py`; its value is the wording users see.
4. Read thresholds from `RuleConfig`, not from constants inside the rule.
5. Register the rule in the `LogicManager` rule list and add a test for when it fires and when it does not.

## How to add a data backend

1. Subclass `DataManager` in a new file in `data_layer/` and implement `save`, `find` and `find_route_history`. Raise `StorageError` for every failure, never the driver's own errors.
2. Use `RecordSerializer` to turn records into documents and back.
3. Add the backend to the `data` fixture in `tests/test_data_managers.py` so the whole contract suite runs against it.
4. Choose it in `build_data()` in `main.py` with a new `DATA_BACKEND` value, and add any settings to `.env.example` with empty values.

## Run the tests

```bash
python -m pytest -q
```

Run them on Python 3.10 or newer before each commit. Tests never use the network, the live Gemini API or a real MongoDB: use `Mock(spec=...)`, `mongomock` and a temp-file `JsonDataManager`. Web tests use FastAPI's `TestClient`.
