# Agent notes (INF1103 Team 4, Supply Chain Risk Assessor)

Read `docs/io-design.md` before touching the IO layer. It holds the agreed design, the decisions and why.

## Rules for the IO layer (`io_layer/`)

- One class per file. Keep code simple: no padding classes, no speculative abstractions.
- Attributes are private (`self.__name`) with properties where needed.
- `IOManager` takes raw strings in and returns plain dicts out. It never prints, never calls the AI, Logic or storage writes, and only reads saved records through `DataManager.find(criteria)`.
- The web layer stays thin: it passes form fields to `IOManager` and renders what comes back. No parsing or rules in routes.
- Dates are `DD/MM/YYYY` only. Ports come only from `ports_reference_4.json` (50 ports).
- Shipment IDs are generated (`SHP-001`, `SHP-002`, ...). A `shipment_id` column in an uploaded CSV is ignored.
- The old `io_manager.py` (questionary CLI) and `validator.py` stay untouched until the final swap PR.
- `Port`, `PortRegistry`, `Shipment`, `SearchCriteria` and `StorageError` in `io_layer/` are placeholders for the shared model and the Data manager. Do not grow them.

## Tests

- Tests live in `tests/` and are named `test_*.py`. Run `pytest -q` from the repo root.
- Tests must run with no network, no live Gemini and no live MongoDB.

## Git

- Work on a `feature/<manager>-<topic>` branch, never on `main`. Pull the latest `main` before starting.
- Every commit message starts with `Ming An 2603225, ` followed by an imperative summary.
- No `Co-Authored-By` lines and no AI attribution in commits, PRs or code.
- Small commits, one logical change each. Never push without asking first.
