# Agent notes (INF1103 Team 4, Supply Chain Risk Assessor)

Read `docs/io-design.md` before touching the IO layer and `docs/handoff.md` for how the app fits together.

## Packages

| Package | What is in it |
|---|---|
| `model/` | Shared model: `Port`, `PortRegistry`, `Shipment`, `RiskFactor`, `Insight`, `AIAssessment`, `Decision`, `ShipmentRecord`, `SearchCriteria`, `StorageError`, and the enums `RiskLevel`, `RiskType`, `Outcome`, `AIStatus`, `Flag` |
| `io_layer/` | `IOManager`, `ShipmentSource` (ABC), `FormSource`, `CsvSource`, `SourceError`, `ShipmentValidator`, `ValidationResult`, `Preview` |
| `data_layer/` | `DataManager` (ABC), `JsonDataManager` (default), `MongoDataManager`, `UnavailableDataManager`, `RecordSerializer` |
| `ai_layer/` | AI manager (PR 2) |
| `logic_layer/` | Logic manager and rules (PR 3) |
| `web/` | `app.py` (`create_web_app`, the FastAPI routes), `templates/`, `static/` |
| `main.py` | Composition root: `assess_shipments`, `build_data`, `build_ai`, `build_logic`, `create_app` |
| `tests/` | pytest tests, `helpers.py`, `fakes.py` (FakeAI and FakeLogic, used by tests and demo mode) |

The old modules at the top level (`io_manager.py`, `validator.py`, `ai_manager.py`, `logic_manager.py`, `data_manager.py`, `mongodb.py`, `config.py`, `feeds.py`, `cache.py`) stay untouched until the final swap PR.

## Rules for the IO and web layers

- One class per file. Keep code simple: no padding classes, no speculative abstractions.
- Attributes are private (`self.__name`) with properties where needed. Type hints and a short docstring on public classes and methods.
- `IOManager` takes raw strings in and returns plain dicts out. It never prints, never calls the AI, Logic or storage writes, and only reads saved records through `DataManager.find(criteria)`.
- The web layer stays thin: it passes form fields to `IOManager` and renders what comes back. No parsing or rules in routes. `web/` never imports `main`; the assessment runner is passed in.
- Jinja autoescape stays on; never use `|safe` on data. Risk and outcome are shown as text, not colour alone.
- Dates are `DD/MM/YYYY` only. Ports come only from `ports_reference_4.json` (50 ports). Times are timezone-aware UTC inside the app.
- Shipment IDs are generated (`SHP-001`, `SHP-002`, ...). A `shipment_id` column in an uploaded CSV is ignored.

## Tests

- Tests live in `tests/` and are named `test_*.py`. Run `python -m pytest -q` from the repo root on Python 3.10 or newer.
- Tests must run with no network, no live Gemini and no live MongoDB.

## Git

- Work on a `feature/<manager>-<topic>` branch, never on `main`. Pull the latest `main` before starting.
- Every commit message starts with `Ming An 2603225, ` followed by an imperative summary.
- No `Co-Authored-By` lines and no AI attribution in commits, PRs or code.
- Small commits, one logical change each. Never push without asking first.
