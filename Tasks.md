# Market Incident Impact Tracker: Requirements

**One-liner:** Detect market-moving events in the news, find which companies they affect (directly and through knock-on effects), and measure the real impact on their stock, separated from general market noise.

**User:** A busy, non-technical investor or employee who holds shares and wants to know: *"Did this news actually hurt or help something I own, and by how much?"*

---

## Pipeline

```
news → extract event + affected companies → resolve tickers → event study → track daily → UI
```

## Must have (MVP)

- [ ] **Event extraction:** reuse `collect_news()`, widened from deals to incidents (M&A, breach, recall, outage, lawsuit, regulation)
- [ ] **LLM returns strict JSON** for each event (schema below)
- [ ] **Knock-on mapping:** the LLM lists indirect companies (competitors, suppliers, customers) with an expected direction (+/−) and a one-line reason
- [ ] **Ticker resolution:** reuse `get_company_symbol()`; tickers for the demo events are **hard-coded and checked by hand**
- [ ] **`run_event_study(ticker, event_date)`**
  - estimation window: day −120 to −10 (fit alpha and beta against the index)
  - abnormal return = actual return − (alpha + beta × market return)
  - CAR (cumulative abnormal return) over day 0 to +N
  - t-stat = CAR ÷ (residual std × √days); significant if |t| ≥ 2
- [ ] **Predicted vs actual:** compare the LLM's predicted direction with the measured CAR ("predicted ↓, market agreed")
- [ ] **UI:** watchlist → alert feed → event page (chart with stock, expected and CAR lines, plus a plain-English verdict sentence)
- [ ] **Cached price data** for the demo events, so a live API failure doesn't break the demo

## Should have (if time)

- [ ] Track button: re-run the event study daily so the impact builds up over time
- [ ] Live pickup of today's news, marked "early, keep tracking"
- [ ] Optional TL;DR, reusing `generate_TLDR()`

## Won't do today

- Historical lookup of similar past events
- Accounts, logins, deployment
- Non-stock data (commodities, FX)

---

## Event JSON schema

```json
{
  "event_id": "string",
  "event_type": "merger | breach | recall | outage | lawsuit | regulation | other",
  "headline": "string",
  "event_date": "YYYY-MM-DD",
  "source_url": "string",
  "direct_companies": [{"name": "string", "ticker": "string|null", "expected_direction": "up|down|unclear"}],
  "knock_on_companies": [{"name": "string", "ticker": "string|null", "relation": "competitor|supplier|customer|other", "expected_direction": "up|down|unclear", "reason": "string"}]
}
```

## Event study output

```json
{
  "ticker": "string", "event_date": "YYYY-MM-DD", "beta": 0.0,
  "raw_return_pct": 0.0, "market_return_pct": 0.0, "expected_return_pct": 0.0,
  "car_pct": 0.0, "t_stat": 0.0, "is_significant": true,
  "daily": [{"day": 0, "actual_pct": 0.0, "expected_pct": 0.0, "abnormal_pct": 0.0}]
}
```

---

## Roles

| Person | Owns |
|---|---|
| A | News query, LLM extraction prompt and JSON, knock-on mapping |
| B | `run_event_study()`, price caching, predicted-vs-actual check |
| C | UI (watchlist, feed, event page), demo data, pitch |

## Timeline (6h)

| Time | Milestone |
|---|---|
| 0:00–0:20 | Agree on the JSON contracts above, set up the repo, pick 2 demo events |
| 0:20–2:30 | Build in parallel (C uses mock JSON until A and B are ready) |
| 2:30–3:30 | **Integrate end to end**, even if it's ugly |
| 3:30–4:45 | Polish: verdict sentence, knock-on view, live pickup |
| 4:45 | **Feature freeze** |
| 4:45–5:30 | Pitch slides, rehearse twice |
| 5:30–6:00 | Record a backup demo video, buffer |

## Demo events

- [ ] **Event 1:** 2–3 weeks old, so the full impact curve exists. Include one knock-on company the market moved.
- [ ] **Event 2:** today or yesterday, to show the live pipeline. Mark the impact as "early".

---

## Judging checklist

- [ ] **Innovation:** not a dashboard. Measures the event's *own* effect and finds knock-on companies a human would miss
- [ ] **Impact:** clear user (shareholders and employees), clear action (should I worry or act?)
- [ ] **Technical depth:** real prices, a standard event-study method we can explain in one sentence: *"we learn how the stock normally moves with the market, then measure only what's left over"*
- [ ] **Demo:** show the data driving the result live, and tell one story end to end

## Known risks

| Risk | Mitigation |
|---|---|
| NewsAPI free tier is delayed 24h and allows 100 requests/day | Cache demo articles; be upfront if asked |
| yfinance rate-limits mid-demo | Cache prices before the demo |
| Wrong ticker match | Hard-code demo tickers |
| No post-event data for today's event | Use a 2–3-week-old event as the main demo |
| "Is this financial advice?" | Present it as information on what happened, not a recommendation |
