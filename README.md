# INF1103-Group-4
“Our goal is simple: give supply chain planners confidence before a shipment leaves the dock — not just an ETA, but a clear picture of what could go wrong and what to do about it.”

"The application uses AI primarily to gather, analyse, and structure information from shipment data and external sources. The AI does not make the final operational decision, that responsibility stays with the Logic Manager."

## Run the web app

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt
cp .env.example .env                 # then fill in what you need; every value may stay empty
uvicorn main:create_app --factory --reload
```

Open http://127.0.0.1:8000. `python main.py` starts the same app without `--reload`.

- **Demo mode:** set `DEMO_MODE=1` in `.env` (or run `DEMO_MODE=1 uvicorn main:create_app --factory`). The app then uses a fake AI and fake rules, so you can try the whole flow without a Gemini key. Every page shows a yellow "Demo mode" banner.
- **Storage:** records are saved to `shipment_records.json` by default. To use MongoDB, set `DATA_BACKEND=mongo`, `MONGO_URI` and `DB_NAME`. If MongoDB cannot be reached, the app still starts and shows a red banner.
- **Try it:** upload `sample_data/shipments.csv` (20 shipments) on the first page, then open **Search**.

## Run the tests

```bash
python -m pytest -q
```

The tests use no network, no live Gemini and no real MongoDB (`mongomock` stands in).

More for teammates: [docs/handoff.md](docs/handoff.md).
