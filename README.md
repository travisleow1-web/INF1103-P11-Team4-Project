# INF1103-Group-4
“Our goal is simple: give supply chain planners confidence before a shipment leaves the dock — not just an ETA, but a clear picture of what could go wrong and what to do about it.”

"The application uses AI primarily to gather, analyse, and structure information from shipment data and external sources. The AI does not make the final operational decision, that responsibility stays with the Logic Manager."

## Run the web app

You need Python 3.10 or newer.

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn main:Application.create --factory --reload
```

Open http://127.0.0.1:8000. `python main.py` starts the same app without `--reload`.

- **For real:** put your Gemini key in `.env` as `GEMINI_API_KEY=...` (optionally `GEMINI_MODEL` and `AI_CACHE_FILE`). Each shipment is then assessed by Gemini with live weather and news, and decided by the rules. If Gemini cannot be reached or its answer is unusable, the shipment is marked "AI unavailable" and sent to a human (ESCALATE). A weather or news feed that fails is sent to Gemini as empty (null) data. Without a key the app still validates shipments but says the AI is not connected.
- **Storage:** records are saved to `shipment_records.json` by default (`DATA_FILE` changes it). To use MongoDB, set `DATA_BACKEND=mongo`, `MONGO_URI` and `DB_NAME`. If MongoDB cannot be reached, the app still starts and shows a red banner.
- **Demo mode:** set `DEMO_MODE=1` in `.env` (or run `DEMO_MODE=1 uvicorn main:Application.create --factory`). The app then uses a fake AI and fake rules, so you can try the whole flow without a Gemini key. Every page shows a yellow "Demo mode" banner. Demo records are kept in `demo_records.json`, apart from real ones.
- **Try it:** upload `sample_data/shipments.csv` (20 shipments) on the first page, then open **Search**.

## Run the tests

```bash
python -m pytest -q
```

The tests use no network, no live Gemini and no real MongoDB (`mongomock` stands in).

## Run with Docker

Nothing needs to be installed except Docker. From the repository root:

```bash
docker build -t supply-chain-risk .

# The app at http://localhost:8000, with the fake AI (no key needed)
docker run --rm -p 8000:8000 -e DEMO_MODE=1 supply-chain-risk

# The app with live Gemini: put GEMINI_API_KEY in .env first (copy .env.example)
docker run --rm -p 8000:8000 --env-file .env supply-chain-risk

# The automated tests inside the container
docker run --rm supply-chain-risk python -m pytest -q
```

Settings are passed at run time with `-e` or `--env-file`, never baked into the image: `.dockerignore` keeps `.env` and saved records out of it. All settings are listed in [.env.example](.env.example).

| Variable | Needed? | What it does |
|---|---|---|
| `GEMINI_API_KEY` | For live AI | Gemini API key. Without it the app validates shipments but says the AI is not connected. |
| `DEMO_MODE` | No | `1` uses the fake AI and rules from `tests/fakes.py`. |
| `DATA_BACKEND` | No | `json` (default) or `mongo`. |
| `DATA_FILE` | No | JSON records file (default `shipment_records.json`). |
| `MONGO_URI`, `DB_NAME` | With `mongo` | MongoDB connection. If it cannot be reached, the app still starts and shows a banner. |
| `GEMINI_MODEL`, `AI_CACHE_FILE` | No | Gemini model name and AI cache file. |

Records saved inside a container are lost when it is removed. To keep them, mount a folder and point `DATA_FILE` at it:
`docker run --rm -p 8000:8000 --env-file .env -v "$PWD/data:/data" -e DATA_FILE=/data/shipment_records.json supply-chain-risk`

## Continuous integration

[.github/workflows/ci.yml](.github/workflows/ci.yml) runs on every push and pull request:

1. **Tests:** installs `requirements.txt` and runs `python -m pytest -q` on Python 3.10 and 3.12.
2. **Docker:** builds the image, runs the tests inside the container, then starts the app in demo mode and checks that it answers on port 8000.

The results are on the repository's **Actions** tab.

More for teammates: [docs/handoff.md](docs/handoff.md).
