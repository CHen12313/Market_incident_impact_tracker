# Chen: Pipeline

**Owns:** `Pipeline/` and `Data_Cache/`
**Contract with the team:** the pipeline writes one JSON file per event to `Data_Cache/events/{event_id}.json`, in the shape shown in section 4. Ding serves these files unchanged, and Xuan renders them. The server does no analysis.

```
Pipeline/
  main.py               run_pipeline / stream_pipeline / refresh_event, plus CLI
  pipeline_module.py    copied from Job-finding-bot
  event_study.py        run_event_study()
  config.py             reads .env
  modules/
Data_Cache/
  events/*.json         written by you, read by Ding
  prices/*.csv          price cache, so the demo works offline
```

---

## 0. Setup (first 20 min)

- [ ] Hand-write `Data_Cache/events/mock_event.json` in the section 4 shape and **commit it first**, so Ding and Xuan aren't blocked on you
- [ ] Stop tracking `.venv` in git: `git rm -r --cached .venv && echo ".venv/" >> .gitignore`
- [ ] `report_generator.py` imports `config`, `transcript_crawler` and `additional_info_collector`, and none of them are in the repo, so it crashes on import. Add `additional_info_collector.py`, write `config.py` (load keys from `.env`), and delete the `transcript_crawler` import (the macro section isn't needed)
- [ ] Pick the 2 demo events: event 1 from 2–3 weeks ago, event 2 from today or yesterday

## 1. Port the skeleton from Job-finding-bot

- [ ] Copy `pipeline_module.py`, `execute_pipeline` and `stream_generator` into `Pipeline/main.py`, renamed `run_pipeline` / `stream_pipeline`
- [ ] Remove `user_id`, quota, `seen_jobs_dict`, the PDF step, and `run_uuid` (Ding generates the `run_id`)
- [ ] Keep the status event protocol unchanged (`progress`, `info` with `tag`, a terminal `result`). Ding streams these to the UI
- [ ] Sync code (`requests`, `yfinance`, the sync OpenAI client) inside an async `run()` must go through `await asyncio.to_thread(...)`

## 2. Modules (in this order)

| Module | Reads | Writes | Reuse |
|---|---|---|---|
| `NewsCollector` | `event_types`, `days_back` | `data["articles"]` | `collect_news()`, with the deal terms swapped for incident terms (breach, recall, outage, lawsuit, regulation, merger) |
| `EventExtractor` | `articles` | `data["events"]` | prompt from `choose_best_news_with_gpt()`, changed to return strict JSON (`response_format={"type": "json_object"}`). Validate it, and drop invalid events instead of crashing |
| `TickerResolver` | `events` | a ticker on each company | `get_company_symbol()`, but check a `DEMO_TICKER_OVERRIDES` dict first. Drop companies with no ticker |
| `EventStudyRunner` | `events` | `data["impacts"]` | new: `run_event_study()` |
| `PredictionChecker` | `impacts` | `prediction_match`, `verdict_text` | new |
| `EventWriter` | everything | `Data_Cache/events/{event_id}.json` | new; write to a temp file, then `os.replace` |

- `event_id` format: `{event_date}-{short-slug}`, e.g. `2026-10-21-acme-data-breach`
- Have `EventExtractor` cap knock-on companies at 4 per event, each with a one-line `reason`

## 3. `run_event_study(ticker, event_date, days_after=10, market_ticker=None)`

- [ ] Prices come from the `Data_Cache/prices/{ticker}.csv` cache first, then yfinance (save what you fetch). The demo must not depend on live yfinance
- [ ] Event day 0 = the first trading day on or after `event_date`, since news often lands after market close or at weekends
- [ ] Market index: `^GSPC` for US tickers; `^FTSE` for `.L`; `^STOXX50E` for `.PA` / `.DE` / `.AS`
- [ ] Estimation window: trading days −120 to −10. Fit with `np.polyfit(market_returns, stock_returns, 1)` to get beta and alpha, and keep the residual std
- [ ] For each day from −10 to +N: actual, expected = alpha + beta × market, abnormal = actual − expected
- [ ] Cumulative values rebased so day −1 = 0. CAR (cumulative abnormal return) starts at day 0 and is `null` before it
- [ ] t = CAR ÷ (residual std × √n_post_days); significant if |t| ≥ 2
- [ ] `status = "early"` if there are fewer than 5 post-event trading days
- [ ] Sanity check: run it on demo event 1 and check one day's numbers by hand

### `verdict_text` and `prediction_match`

- Significant: `"Fell 6.2% more than the market explains over 10 trading days (t = −3.4): very unlikely to be noise."`
- Not significant: `"Moved roughly in line with the market: no clear effect from this event (t = 0.8)."`
- `prediction_match`: `true` if significant and the sign matches `expected_direction`; `false` if significant and the sign is opposite; `null` if not significant or the direction is `unclear`

## 4. Output shape (shared contract: don't change it after 0:20 without telling the team)

```json
{
  "event": {
    "event_id": "2026-10-21-acme-data-breach",
    "event_type": "merger | breach | recall | outage | lawsuit | regulation | other",
    "headline": "string",
    "summary": "one sentence",
    "event_date": "YYYY-MM-DD",
    "source_url": "string"
  },
  "status": "complete | early",
  "generated_at": "ISO-8601 datetime",
  "impacts": [
    {
      "company_name": "string",
      "ticker": "string",
      "relation": "direct | competitor | supplier | customer | other",
      "expected_direction": "up | down | unclear",
      "reason": "string",
      "prediction_match": true,
      "study": {
        "market_ticker": "^GSPC",
        "event_day": "YYYY-MM-DD",
        "days_after": 10,
        "beta": 1.21,
        "raw_return_pct": -7.4,
        "market_return_pct": -1.0,
        "expected_return_pct": -1.2,
        "car_pct": -6.2,
        "t_stat": -3.4,
        "is_significant": true,
        "verdict_text": "string",
        "daily": [
          {"day": -10, "date": "YYYY-MM-DD", "actual_pct": 0.3, "expected_pct": 0.2, "abnormal_pct": 0.1,
           "cum_actual_pct": -0.5, "cum_expected_pct": -0.4, "car_pct": null}
        ]
      }
    }
  ]
}
```

## 5. Entry points Ding calls

- [ ] `async def stream_pipeline(params)`: async generator that yields status events, ending with `{"type": "result", "success": bool, "event_ids": [...]}`. `params = {"event_types": [...], "days_back": 3}`
- [ ] `def refresh_event(event_id) -> dict`: re-runs the study for every ticker in that file, rewrites it, and returns the new content (used by the Refresh and Track buttons)
- [ ] `python3 -m Pipeline.main --demo`: regenerates both demo event files from the cache

## Milestones

| Time | Done |
|---|---|
| 0:20 | `mock_event.json` committed, demo events picked |
| 1:30 | `run_event_study()` correct for every demo event 1 ticker |
| 2:30 | Full pipeline writes real files for both demo events → **integration with Ding and Xuan** |
| 3:30–4:45 | Knock-on quality, verdict wording, a live run on today's news |
| 4:45 | Feature freeze |

**Not today:** TL;DR, historical lookup of similar events, non-stock data.
