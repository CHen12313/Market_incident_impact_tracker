# Market_incident_impact_tracker
An app that scrapes news from media, extract incidents, and allows users to track the impact of those incidents and make quick decisions.

## Running locally

Backend (Flask API, from the repo root):

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m Server.app
```

This serves `http://127.0.0.1:5000`.

Frontend (in a second terminal):

```sh
npm ci --prefix Frontend
npm run dev --prefix Frontend
```

Vite's dev server proxies API calls to the Flask backend above.

Run the test suite with:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

### API keys

Create a `.env` file in the repo root (see `Server/README.md` for the full list of variables). Without `NEWS_API_KEY` and `OPENAI_API_KEY` set, the live news scan ("Scan latest news") and event extraction will fail outright — the pipeline raises an error as soon as a scan is started. `ALPHA_VANTAGE_API_KEY` and `FINNHUB_API_KEY` are optional fallbacks for price data.

You can still run and explore the app without any keys: `Data_Cache/events/` ships with sample events, price lookups fall back to Yahoo Finance (no key required), and refreshing an already-tracked event's price history works without `NEWS_API_KEY`/`OPENAI_API_KEY` since it doesn't re-run the news/LLM steps.

See `Server/README.md` for more detail on the Flask/Pipeline integration.
