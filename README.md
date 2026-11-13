# INF1103-Group-4
“Our goal is simple: give supply chain planners confidence before a shipment leaves the dock — not just an ETA, but a clear picture of what could go wrong and what to do about it.”

"The application uses AI primarily to gather, analyse, and structure information from shipment data and external sources. The AI does not make the final operational decision, that responsibility stays with the Logic Manager."

## Run the web app

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn main:create_app --factory --reload
```

Open http://127.0.0.1:8000. `python main.py` starts the same app without `--reload`.

- **For real:** put your Gemini key in `.env` as `GEMINI_API_KEY=...` (optionally `GEMINI_MODEL` and `AI_CACHE_FILE`). Each shipment is then assessed by Gemini with live weather and news, and decided by the rules. If Gemini cannot be reached or its answer is unusable, the shipment is marked "AI unavailable" and sent to a human (ESCALATE). A weather or news feed that fails is sent to Gemini as empty (null) data. Without a key the app still validates shipments but says AI and Logic are not connected.
- **Storage:** records are saved to `shipment_records.json` by default (`DATA_FILE` changes it). To use MongoDB, set `DATA_BACKEND=mongo`, `MONGO_URI` and `DB_NAME`. If MongoDB cannot be reached, the app still starts and shows a red banner.
- **Demo mode:** set `DEMO_MODE=1` in `.env` (or run `DEMO_MODE=1 uvicorn main:create_app --factory`). The app then uses a fake AI and fake rules, so you can try the whole flow without a Gemini key. Every page shows a yellow "Demo mode" banner. Demo records are kept in `demo_records.json`, apart from real ones.
- **Try it:** upload `sample_data/shipments.csv` (20 shipments) on the first page, then open **Search**.

## Run the tests

```bash
python -m pytest -q
```

The tests use no network, no live Gemini and no real MongoDB (`mongomock` stands in).

More for teammates: [docs/handoff.md](docs/handoff.md).
