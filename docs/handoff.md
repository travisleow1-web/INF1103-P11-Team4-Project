# Handoff guide for teammates

How the Phase 2 app is put together, and where your part plugs in.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env
DEMO_MODE=1 uvicorn main:create_app --factory --reload
```

Open http://127.0.0.1:8000, upload `sample_data/shipments.csv`, then try **Search**. To run with the real AI and rules, see the README.

## Demo mode

`DEMO_MODE=1` makes `create_app()` use `FakeAI` and `FakeLogic` from `tests/fakes.py` instead of the real managers, and every page shows a yellow banner "Demo mode: fake AI and rules". Demo records go to `DEMO_DATA_FILE` (default `demo_records.json`), never to `DATA_FILE` or MongoDB, so demo runs cannot mix with real records. The fakes give each shipment a low, medium or high weather risk based on its number. They live under `tests/` and never run unless demo mode is on.

Without demo mode, the AI comes from `build_ai()` and the Logic from `build_logic()` in `main.py`. `build_ai()` returns `None` when `GEMINI_API_KEY` is not set; the home page then says so up front, and the submit page validates the rows and then says "N shipments are valid. AI and Logic are not connected yet."

## Folder map

| Folder or file | What is in it |
|---|---|
| `model/` | The shared model, one class per file: `Port`, `PortRegistry`, `Shipment`, `RiskFactor`, `Insight`, `AIAssessment`, `Decision`, `ShipmentRecord`, `SearchCriteria`, `StorageError`, and the enums `RiskLevel`, `RiskType`, `Outcome`, `AIStatus`, `Flag` |
| `io_layer/` | `IOManager` (validation, ID numbering, search, display dicts), `FormSource` and `CsvSource`, `ShipmentValidator`, `Preview`, `ValidationResult`, `SourceError`. Design notes: `docs/io-design.md` |
| `data_layer/` | `DataManager` (ABC) with `JsonDataManager` (default), `MongoDataManager` and `UnavailableDataManager`; `RecordSerializer` |
| `ai_layer/` | `AIManager`, `GeminiClient`, `ContextProvider` (ABC) with `WeatherProvider` and `NewsProvider`, `ResponseParser`, `ResponseCache`, the errors, and the prompt and schema constants in `ai_settings.py` |
| `logic_layer/` | `LogicManager`, `RuleConfig`, `BusinessRule` (ABC) and its rules, `OutcomeResolver` |
| `web/app.py` | `create_web_app(..., run=...)`: the FastAPI routes `GET /`, `POST /submit`, `GET /search`. `main.create_app` passes `assess_shipments` as `run`, so `web/` never imports `main` |
| `web/templates/` | Jinja templates. `_header.html` and `_footer.html` wrap every page; `_macros.html` holds the badges and the details row |
| `web/static/` | `style.css` and `add_row.js` (the only JavaScript) |
| `main.py` | Composition root: `assess_shipments`, `build_data`, `build_ai`, `build_logic`, `create_app` |
| `tests/` | pytest tests, `helpers.py` (shared test data) and `fakes.py` (FakeAI, FakeLogic) |

The flow for one submission: the route calls `io.preview(...)`. If every row is valid, `main.assess_shipments` runs, for each shipment, `ai.assess` then `logic.evaluate` then `data.save`, and yields `(record, save_error)`. The route streams one table row per shipment. The managers never call each other; only `main.py` knows all of them.

## How the AI and Logic layers are connected

- **AI:** `build_ai()` in `main.py` builds `AIManager` (`ai_layer/`) from `GEMINI_API_KEY`, `GEMINI_MODEL` and `AI_CACHE_FILE`, and returns `None` without a key. `assess(shipment)` always returns an `AIAssessment`; when Gemini fails it returns `AIAssessment.fallback()`, which the pages mark "AI unavailable". The design is in the team notes (`ai-manager-design-notes.md`); add a news or weather source as a new `ContextProvider` subclass.
- **Logic:** `build_logic(data, ports)` returns `LogicManager(data, ports)` with the default thresholds. `evaluate(shipment, assessment, now)` returns a `Decision`; route history comes from `data.find_route_history(route_id, since)`.

## Storage problems

If MongoDB is chosen but cannot be reached (or `MONGO_URI`/`DB_NAME` are missing or invalid), the app still starts with an `UnavailableDataManager`: every page shows a red "Database unavailable. Results will not be saved." banner, and the submit page refuses to number shipments until saved records can be read. The detail is in the log.

## How to add a page

1. Add a template in `web/templates/` that starts with `{% set title = "..." %}{% include "_header.html" %}` and ends with `{% include "_footer.html" %}`.
2. Add a route inside `create_web_app` in `web/app.py` that collects the raw fields, calls one `IOManager` method and returns `page(request, "your_page.html", ...)`. Keep parsing and rules out of the route.
3. If the page needs new display data, add a `show_...` method to `IOManager` that returns a plain dict.
4. Link it from the navigation in `_header.html`, label every input, and add a test in `tests/test_web.py`.

Jinja autoescape is on. Never use `|safe` on data, and show risk and outcome as text, not only as colour.

## The Logic layer

The Logic layer is based on Jun Jie's `Logic_ManagerPart2` branch (one `logic_manager.py` with 15 classes). It was split into one class per file and keeps his class names, thresholds and rule order. His `RecordPreparer` and `RecordValidator` were dropped because the AI parser returns validated objects, and `RouteHistorySource` because `DataManager.find_route_history` does that job.

`LogicManager.evaluate` runs the rules in this order, each in its own `try`/`except` (a rule that raises becomes a "Rule error" note with human review), then `OutcomeResolver`:

| Rule | What it does |
|---|---|
| `DataQualityRule` | FALLBACK, low confidence, outdated data or conflicting sources: flag and human review |
| `PerfectStormRule` | A High or Extreme factor raises the risk to it; enough Medium weather, congestion and labour factors make it High ("Perfect Storm") |
| `AIInsightRule` | Data-quality insight codes need a human; long `POTENTIAL_DELAY`s and High or Extreme `MULTIPLE_RISKS` raise the risk |
| `InsuranceRule` | Piracy or severe civil unrest: hold, High, "Premium Increase Required" |
| `UnregisteredLocationRule` | Notes factor and insight locations that are not in the port list |
| `RouteHistoryRule` | Still Low, but the route had risk above Low or a delay recently: hold for dispatcher sign-off ("Cautionary Override") |
| `ProcurementRule` | Cargo Destruction at the origin port: hold and alert procurement |

`OutcomeResolver` then picks one outcome: Extreme risk is REJECT; a Procurement Alert is DELAY; a Premium Increase is INSURE; High is DELAY; otherwise PROCEED. A held or human-review shipment never proceeds automatically (ESCALATE).

**Thresholds** live in `RuleConfig` (`confidence_min`, `history_window_days`, `perfect_storm_min_mediums`, `data_max_age_hours`, `delay_days_limit`, `delay_days_high`). It validates every value and raises `ValueError` on a bad one; `to_dict()`/`from_dict()` save and load it, and `LogicManager.update_config(config)` applies a new one. To add a threshold, add it to the defaults in `rule_config.py` with a property and a check.

**To add a rule:**

1. Add a `BusinessRule` subclass in its own file in `logic_layer/` and implement `apply(shipment, assessment, decision, now)`. Take any thresholds (`RuleConfig`) or services (such as the `DataManager`) in the constructor.
2. Change the decision only through its methods: `raise_risk`, `add_note(why, flag, action, human)`, `hold`, `require_human`, `add_alert`, `add_action`. Risk only goes up. Leave the outcome to `OutcomeResolver`.
3. Use a `Flag` member for any flag. A new flag needs a new member in `model/flag.py`; its value is the wording users see.
4. Add the rule to the list in `LogicManager` and a test file `tests/test_<rule>.py` for when it fires and when it does not (`tests/logic_fixtures.py` builds typed shipments and assessments).

## How to add a data backend

1. Subclass `DataManager` in a new file in `data_layer/` and implement `save`, `find` and `find_route_history`. Raise `StorageError` for every failure, never the driver's own errors, and keep its message short (log the driver's detail). Skip and log a damaged record in `find` instead of failing the whole list, and refuse a naive `since` with `ValueError`.
2. Use `RecordSerializer` to turn records into documents and back.
3. Add the backend to the `data` fixture in `tests/test_data_managers.py` so the whole contract suite runs against it.
4. Choose it in `build_data()` in `main.py` with a new `DATA_BACKEND` value, and add any settings to `.env.example` with empty values.

## Run the tests

```bash
python -m pytest -q
```

Run them on Python 3.10 or newer before each commit. Tests never use the network, the live Gemini API or a real MongoDB: use `Mock(spec=...)`, `mongomock` and a temp-file `JsonDataManager`. Web tests use FastAPI's `TestClient`.
