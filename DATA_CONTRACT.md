# Data Contract

Everything that crosses a boundary between the three parts of the app: the
pipeline (`Pipeline/`, Chen), the Flask server (`Server/`, Ding) and the React
SPA (`Frontend/`, Xuan). Three contracts, one per boundary:

```
Pipeline ──Event File Contract──────────▶ Data_Cache/events/*.json ──served as-is──▶ Frontend
Pipeline ──Pipeline Status Event Protocol──▶ Server ──Client Stream Frame Protocol──▶ Frontend
```

**Version 1**, frozen at 0:20. Any change: tell all three people first, then
bump the version here. The Chinese copy is [DATA_CONTRACT_CN.md](DATA_CONTRACT_CN.md);
if the two disagree, this file wins. A complete example of an event file is
`Data_Cache/events/2026-10-20-mock-nimbus-cloud-outage.json`.

## Contents

- [Event File Contract — pipeline → server → frontend](#event-file-contract--pipeline--server--frontend)
  - [Conventions](#conventions)
  - [Full event file](#full-event-file)
  - [`event` — what happened](#event--what-happened)
  - [`impacts` — who was affected](#impacts--who-was-affected)
  - [`study` — the event-study result](#study--the-event-study-result)
  - [`daily` — per-day rows for the chart](#daily--per-day-rows-for-the-chart)
  - [`prediction_match` / `verdict_text` — the plain-English layer](#prediction_match--verdict_text--the-plain-english-layer)
  - [`status` — complete vs early](#status--complete-vs-early)
  - [Invariants](#invariants)
  - [Mock files](#mock-files)
- [Event summary — server-built list items](#event-summary--server-built-list-items)
- [`stream_pipeline` — input and result](#stream_pipeline--input-and-result)
  - [`pipeline_params` — input to `stream_pipeline`](#pipeline_params--input-to-stream_pipeline)
  - [`stream_pipeline`'s result shapes](#stream_pipelines-result-shapes)
- [Pipeline Status Event Protocol — pipeline → server status events](#pipeline-status-event-protocol--pipeline--server-status-events)
- [Client Stream Frame Protocol — server → frontend SSE frames](#client-stream-frame-protocol--server--frontend-sse-frames)
  - [Wire format](#wire-format)
  - [Frame types](#frame-types)
  - [Translation from the Pipeline Status Event Protocol](#translation-from-the-pipeline-status-event-protocol)
  - [Server behaviour — replay and reconnects](#server-behaviour--replay-and-reconnects)
  - [Client rules](#client-rules)
  - [Polling fallback — `/api/pipeline/status/<run_id>`](#polling-fallback--apipipelinestatusrun_id)
  - [A full run on the wire](#a-full-run-on-the-wire)

## Event File Contract — pipeline → server → frontend

One JSON file per detected event, at `Data_Cache/events/{event_id}.json`. The
file name is always `event_id + ".json"`, so the server can map
`GET /api/events/<event_id>` straight onto a path with no index.

Written **only** by the pipeline's last stage, `EventWriter`, which writes a
temp file and then `os.replace`s it, so the server can never read a
half-written file. Re-written in place by `refresh_event(event_id)` when the
user presses Refresh or Track. The server **only reads** these files and
returns them unchanged; the frontend renders the fields as they are, with no
maths of its own. Every number on screen is computed once, in the pipeline.

How the pipeline builds it, stage by stage (the same `data` dict pattern as
Job-finding-bot's Generator):

```
NewsCollector        adds    articles
EventExtractor       adds    events                  # LLM, response_format json_object; invalid events dropped
TickerResolver       mutates events                  # ticker filled; companies with no ticker dropped
EventStudyRunner     adds    impacts                 # one study per company; a failed study drops that company
PredictionChecker    mutates impacts                 # adds prediction_match, verdict_text
EventWriter          writes  Data_Cache/events/{event_id}.json, adds event_ids
```

That's 6 stages. The `progress` events divide by this count, so it has to
track the pipeline builder.

### Conventions

- **Percentages are in percent units.** `-6.2` means −6.2%. Rounded to 2 dp.
- **Returns are simple daily returns, and cumulative values are sums**, not
  compounded. This is the standard event-study convention, and it's what makes
  `car_pct = raw − expected` hold exactly.
- **`day`** is a trading-day offset from the event. Day 0 is the first trading
  day on or after `event_date`, because news often breaks after the close or at
  a weekend.
- **Dates** are `YYYY-MM-DD` exchange-local trading dates. `generated_at` is
  ISO-8601 UTC (`2026-11-07T11:02:13Z`).
- **Every key is always present.** `null` only appears where a field below
  says so.

### Full event file

Shown as the Python dict `EventWriter` dumps; on disk `True`/`False`/`None`
are `true`/`false`/`null`. Values are from the mock event:

```python
{
    "event": {
        "event_id":    "2026-10-20-mock-nimbus-cloud-outage",
        "event_type":  "outage",
        "headline":    "[MOCK] Nimbus Cloud suffers 14-hour global outage, thousands of business customers offline",
        "summary":     "[MOCK] A failed configuration update took Nimbus Cloud's main regions offline for 14 hours, ...",
        "event_date":  "2026-10-20",
        "source_url":  "https://example.com/mock/nimbus-cloud-outage",
    },
    "status":       "complete",                     # "complete" | "early", see "status"
    "generated_at": "2026-11-07T11:02:13Z",
    "impacts": [                                    # direct companies first, then knock-on by abs(car_pct) desc; never empty
        {
            "company_name":       "Nimbus Cloud Inc.",
            "ticker":             "NMBS",
            "relation":           "direct",
            "expected_direction": "down",
            "reason":             "The company that had the outage; customers may claim credits or switch providers.",
            "prediction_match":   True,
            "study": {
                "market_ticker":       "^GSPC",
                "event_day":           "2026-10-20",
                "days_after":          10,
                "beta":                1.23,
                "raw_return_pct":      -11.76,
                "market_return_pct":   -0.67,
                "expected_return_pct": -0.46,
                "car_pct":             -11.3,
                "t_stat":              -3.9,
                "is_significant":      True,
                "verdict_text":        "Fell 11.3% more than the market explains over 10 trading days (t = -3.9): very unlikely to be noise.",
                "daily": [
                    {"day": -10, "date": "2026-10-06", "actual_pct": 0.23, "expected_pct": -0.91, "abnormal_pct": 1.13,
                     "cum_actual_pct": -1.46, "cum_expected_pct": -1.17, "car_pct": None},
                    # ... one row per trading day ...
                    {"day": -1, "date": "2026-10-19", "actual_pct": -0.25, "expected_pct": -0.01, "abnormal_pct": -0.24,
                     "cum_actual_pct": 0.0, "cum_expected_pct": 0.0, "car_pct": None},
                    {"day": 0, "date": "2026-10-20", "actual_pct": -8.71, "expected_pct": -0.26, "abnormal_pct": -8.45,
                     "cum_actual_pct": -8.71, "cum_expected_pct": -0.26, "car_pct": -8.45},
                    # ...
                    {"day": 10, "date": "2026-11-03", "actual_pct": 0.67, "expected_pct": 0.99, "abnormal_pct": -0.31,
                     "cum_actual_pct": -11.76, "cum_expected_pct": -0.46, "car_pct": -11.3},
                ],
            },
        },
        # ... knock-on companies, same shape ...
    ],
}
```

### `event` — what happened

Produced by `EventExtractor` (LLM) from one or more articles about the same
story. Unchanged by every later stage.

```python
{
    "event_id":   "2026-10-21-acme-data-breach",  # ^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$ — event_date + short slug; also the file name
    "event_type": "breach",                       # merger | breach | recall | outage | lawsuit | regulation | other
    "headline":   "...",                          # the article headline, or the LLM's one-line rewrite of it
    "summary":    "...",                          # one plain-English sentence; shown under the headline
    "event_date": "2026-10-21",                   # the date the news broke — may be a weekend; day 0 is derived from it
    "source_url": "https://...",                  # the original article; copied verbatim, never generated
}
```

### `impacts` — who was affected

One entry per company the LLM linked to the event: the companies named
directly, plus at most 4 knock-on companies. Built by `TickerResolver` and
`EventStudyRunner`, completed by `PredictionChecker`. Sorted with `direct`
first, then knock-on companies by `abs(study.car_pct)` descending, so the
frontend can render the list in order.

```python
{
    "company_name":       "Stratus Systems",
    "ticker":             "STRS",            # Yahoo format: "AAPL", "TSCO.L", "ASML.AS"; resolved via DEMO_TICKER_OVERRIDES, then get_company_symbol()
    "relation":           "competitor",      # direct | competitor | supplier | customer | other
    "expected_direction": "up",              # the LLM's prediction, made BEFORE prices are looked at: up | down | unclear
    "reason":             "Main cloud competitor; likely to win customers looking for a backup provider.",  # one line, LLM
    "prediction_match":   True,              # see "prediction_match / verdict_text"
    "study":              {...},             # see "study"; never None
}
```

A company with no resolvable ticker is dropped by `TickerResolver`. A company
whose study fails (no price data, not enough history for the estimation
window) is dropped by `EventStudyRunner`, which emits an `info` event with
`tag: "warning"` naming it. If an event ends up with no impacts at all,
`EventWriter` doesn't write a file for it.

### `study` — the event-study result

Produced by `run_event_study(ticker, event_date, days_after=10)` in
`Pipeline/event_study.py`. The market model is fitted on trading days −120 to
−10, so the news itself can't leak into what "normal" looks like.

```python
{
    "market_ticker":       "^GSPC",       # ^GSPC for US tickers, ^FTSE for .L, ^STOXX50E for .PA/.DE/.AS
    "event_day":           "2026-10-20",  # the date of day 0 (first trading day on or after event_date)
    "days_after":          10,            # post-event trading days actually included: min(10, days available); drives "status"
    "beta":                1.23,          # slope of stock vs market on days -120..-10 — "how strongly it usually follows the market"
    "raw_return_pct":      -11.76,        # stock move, day 0 to day days_after (= daily[-1].cum_actual_pct)
    "market_return_pct":   -0.67,         # index move over the same days
    "expected_return_pct": -0.46,         # what alpha + beta × market predicted (= daily[-1].cum_expected_pct)
    "car_pct":             -11.3,         # cumulative abnormal return: the event's own effect = raw - expected
    "t_stat":              -3.9,          # car_pct / (residual_std × sqrt(days_after + 1))
    "is_significant":      True,          # abs(t_stat) >= 2
    "verdict_text":        "...",         # see "prediction_match / verdict_text"
    "daily":               [...],         # see "daily"
}
```

### `daily` — per-day rows for the chart

One row per trading day from −10 to `days_after`, in order, so the chart can
show the 10 calm days before the event as well as the reaction. The frontend
plots `cum_actual_pct`, `cum_expected_pct` and `car_pct` directly against `day`.

```python
{
    "day":              0,             # trading-day offset; 0 = event_day
    "date":             "2026-10-20",
    "actual_pct":       -8.71,         # the stock's return that day
    "expected_pct":     -0.26,         # alpha + beta × market return that day
    "abnormal_pct":     -8.45,         # actual - expected, computed before rounding
    "cum_actual_pct":   -8.71,         # running sum of actual_pct, rebased so day -1 = 0
    "cum_expected_pct": -0.26,         # running sum of expected_pct, rebased so day -1 = 0
    "car_pct":          -8.45,         # running sum of abnormal_pct from day 0; None for day < 0
}
```

The day −1 rebase is why every line on the chart starts from 0 just before
the event: anything that happens after that point is the reaction.

### `prediction_match` / `verdict_text` — the plain-English layer

Both are written by `PredictionChecker`, so the frontend never has to decide
what a number means.

`prediction_match` compares the LLM's `expected_direction` with what the
market actually did:

```python
True    # significant, and the sign of car_pct matches expected_direction
False   # significant, but the sign is opposite
None    # not significant, or expected_direction == "unclear" — nothing to check
```

`verdict_text` is one sentence the frontend shows unchanged, in one of two forms:

```python
# is_significant == True
"Fell 11.3% more than the market explains over 10 trading days (t = -3.9): very unlikely to be noise."
"Rose 8.2% more than the market explains over 10 trading days (t = 3.1): very unlikely to be noise."

# is_significant == False
"Moved roughly in line with the market: no clear effect from this event (t = 0.8)."
```

### `status` — complete vs early

```python
"complete"   # days_after >= 5
"early"      # days_after < 5 — today's or yesterday's news; the frontend shows an "Early, still tracking" badge
```

Every impact in one file is studied over the same days, so `status` is a
property of the whole event, not of each company.

### Invariants

`EventWriter` asserts all of these before writing (copy
`check_contract_invariants()` from `scripts/make_mock_event.py`), so the
frontend can rely on them without checking:

1. `daily[0].day == -10` and `daily[-1].day == days_after`
2. The day −1 row has `cum_actual_pct == 0` and `cum_expected_pct == 0`
3. `daily[-1].car_pct == study.car_pct`, and `car_pct ≈ raw_return_pct − expected_return_pct` (±0.05, rounding)
4. `abnormal_pct ≈ actual_pct − expected_pct` (±0.02, rounding)
5. `study.event_day` equals the `date` of the day 0 row
6. `status == "early"` exactly when `days_after < 5`

### Mock files

Two mocks are committed in `Data_Cache/events/`:

```
2026-10-20-mock-nimbus-cloud-outage.json         # complete, 10 days after; covers every UI state
2026-10-20-mock-nimbus-cloud-outage-early.json   # early, 3 days after; for the badge
```

Between them they cover a significant drop, a significant rise, a
not-significant result, and `prediction_match` of `True` / `False` / `None`.
Both come from `python3 scripts/make_mock_event.py [--days-after 3]`, which uses
the same maths as `run_event_study()` and the same invariant checks, just with
simulated prices. Mock `event_id`s contain `-mock-` and headlines start with
`[MOCK]`. **Delete both files before the demo.**

## Event summary — server-built list items

`GET /api/events` and `GET /api/alerts` don't return whole event files (each
one carries 4 × 21 daily rows). The server builds one summary per file:

```python
{
    "event_id":         "2026-10-20-mock-nimbus-cloud-outage",
    "event_type":       "outage",
    "headline":         "...",
    "event_date":       "2026-10-20",
    "status":           "complete",
    "affected_count":   4,                                                     # len(impacts)
    "top_impact":       {"ticker": "NMBS", "car_pct": -11.3, "is_significant": True},  # the impact with the largest abs(car_pct)
    "touches_watchlist": True,                                                 # any impacts[].ticker in watchlist.json
}
```

`/api/alerts` returns only the summaries with `touches_watchlist: True`, each
with one extra key listing the watchlist tickers it hit:

```python
"matched": [
    {"ticker": "NMBS", "relation": "direct",     "car_pct": -11.3, "is_significant": True},
    {"ticker": "STRS", "relation": "competitor", "car_pct": 8.18,  "is_significant": True},
]
```

Both lists are sorted by `event_date`, newest first.

## `stream_pipeline` — input and result

### `pipeline_params` — input to `stream_pipeline`

Built by the server from the `POST /api/pipeline/run` body. Much smaller than
Job-finding-bot's `generator_params`: no user, quota, CV or `seen_jobs_dict`.

```python
{
    "event_types": ["breach", "recall", "outage"],  # optional; defaults to every event_type except "other"
    "days_back":   3,                               # optional, default 3; how far back NewsCollector searches
}
```

`run_id` is minted by the server and **not** passed in. The pipeline doesn't
need it, because the server tags every event it receives (see
[Server behaviour](#server-behaviour--replay-and-reconnects)).

### `stream_pipeline`'s result shapes

`stream_pipeline` yields status events and ends with exactly one `result`
event. Three shapes, not two: as in Job-finding-bot, an early exit is also
`success: True`:

```python
# success — at least one event file was written
{"type": "result", "success": True, "event_ids": ["2026-11-07-acme-recall"], "exit_reason": None}

# early exit — ran cleanly, but found nothing worth writing; still success: True
{"type": "result", "success": True, "event_ids": [], "exit_reason": "No new events found"}

# failure — a module raised
{"type": "result", "success": False, "error_message": "❌ NewsAPI returned 401 for every key"}
```

`event_ids` lists only the files written or re-written by this run, not every
file in `Data_Cache/events/`.

## Pipeline Status Event Protocol — pipeline → server status events

The same protocol as Job-finding-bot's Generator Status Event Protocol: modules
call `self.emit_status(data, message=..., tag=...)`, `execute_pipeline` emits
`progress`, and `stream_pipeline` owns the queue and yields everything in
order. The one addition is `stage` / `stage_label` on `progress`, which the
frontend uses as the progress bar's caption.

- `progress` — `{type, completed, total, stage, stage_label}`. Emitted by
  `execute_pipeline` once before the loop (`completed: 0`, `stage: None`) and
  once after each stage finishes. `stage` is the module's class name, and
  `stage_label` is its `label` class attribute:

  ```python
  {"type": "progress", "completed": 3, "total": 6, "stage": "TickerResolver", "stage_label": "Matching companies to tickers"}
  ```

  ```
  stage                 stage_label
  NewsCollector         Collecting news
  EventExtractor        Extracting events
  TickerResolver        Matching companies to tickers
  EventStudyRunner      Measuring market impact
  PredictionChecker     Checking predictions
  EventWriter           Saving results
  ```

- `info` — `{type, message, tag}`. Emitted via `PipelineModule.emit_status`
  from inside a module's `run`. `tag` is one of `"start"`, `"info"`,
  `"sub_stage_success"`, `"stage_success"`, `"sub_stage_fail"` and `"warning"`;
  the frontend styles each one differently, and unknown tags fall back to
  `"info"`. Warnings (a dropped company, a skipped article) are `info` events
  with `tag: "warning"`, not a separate type:

  ```python
  {"type": "info", "message": "Found 14 articles", "tag": "stage_success"}
  {"type": "info", "message": "⚠️ No price data for XYZ, skipped", "tag": "warning"}
  ```

- `result` — terminal, exactly one per run, yielded last. Shapes are in
  [`stream_pipeline`'s result shapes](#stream_pipelines-result-shapes).

Ordering: the first event is always `progress` with `completed: 0`, and
nothing follows `result`.

## Client Stream Frame Protocol — server → frontend SSE frames

This consumes the Pipeline Status Event Protocol and translates it into the
SSE frames below. It's owned by the server: the background thread that runs
`stream_pipeline` and the stream route `GET /api/pipeline/stream/<run_id>`.

**A frame is not a run.** The pipeline runs in a server-owned background
thread, started by `POST /api/pipeline/run` before any frame exists. A browser
that disconnects or refreshes just stops receiving frames, and the run keeps
going. Unlike Job-finding-bot, a reconnect here **does** catch up: the server
keeps every frame of the run and replays them (see
[Server behaviour](#server-behaviour--replay-and-reconnects)).

### Wire format

Each frame is:

```
id: <seq>
event: <type>
data: <json>

```

- `id` is `seq`, a 0-based counter per run, added by the server
- `event` matches the `type` inside `data`
- `data` is the frame dict, plus `seq`, as one line of JSON
- the frame ends with a blank line

Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
`X-Accel-Buffering: no`. When nothing has been sent for 15 s, the server sends
a comment line, `: ping`, followed by a blank line, so idle connections aren't
dropped. An unknown `run_id` returns `404` with `{"error": "Unknown run_id"}`.

### Frame types

- `progress` — `{type, seq, completed, total, stage, stage_label}`. Forwarded
  unchanged from the Pipeline Status Event Protocol, plus `seq`.
- `info` — `{type, seq, message, tag}`. Forwarded unchanged, plus `seq`.
- `done` — terminal. Two variants:
  - clean: `{type: "done", seq, success: true, event_ids: [...]}`. Frontend:
    close the stream, refresh the event list, and highlight `event_ids`.
  - early exit: `{type: "done", seq, success: true, event_ids: [], exit_reason}`.
    Frontend: close the stream and show `exit_reason` as a neutral message,
    not an error.
- `error` — `{type, seq, message}`. Terminal. Sources: the pipeline failed
  (`result.success` false), the params were rejected (`400` from
  `POST /api/pipeline/run`, so no stream ever exists), or the thread crashed
  without yielding a `result` (message `"Pipeline crashed"`). Frontend: close
  the stream and show the message.

Two invariants:

- `result` never reaches the browser. It's the Pipeline Status Event
  Protocol's terminal type, and the server translates it into `done` or `error`.
- Exactly one terminal frame (`done` or `error`) per run, after which the
  server closes the response.

### Translation from the Pipeline Status Event Protocol

| Pipeline Status Event Protocol | Client Stream Frame Protocol |
|---|---|
| `progress` / `info` | same, plus `seq` |
| `result` (success, `event_ids` non-empty) | `done` |
| `result` (success, `exit_reason` set) | `done` with `exit_reason` |
| `result` (failure) | `error`, with `message` = `error_message` |
| background thread raised with no `result` | `error`, `"Pipeline crashed"` |

### Server behaviour — replay and reconnects

```python
runs[run_id] = {
    "frames": [...],                 # every frame of the run, in order; append-only, never trimmed
    "state":  "running",             # running | done | error — set when the terminal frame is appended
}
```

- The background thread translates each status event as it arrives, adds
  `seq = len(frames)`, and appends it. Nothing is ever removed, so any number
  of clients can read the same run.
- The stream route starts at `Last-Event-ID + 1` if that request header is
  present (the browser sends it automatically when `EventSource` reconnects),
  otherwise at 0. It replays the stored frames, then polls `frames` every
  0.2 s for new ones, and closes the response right after sending the terminal
  frame.
- One run at a time: `POST /api/pipeline/run` returns `409` while a run is
  `running`. That's enough for the demo, and it protects NewsAPI's
  100-requests-a-day quota.

### Client rules

Unlike Job-finding-bot, this stream is a `GET` (the run is started by a
separate `POST`) with no CSRF or session to send, so the frontend uses the
browser's `EventSource` instead of reading `response.body` by hand:

```js
const eventSource = new EventSource(`/api/pipeline/stream/${runId}`);
eventSource.addEventListener("progress", (message) => setProgress(JSON.parse(message.data)));
eventSource.addEventListener("info", (message) => appendLog(JSON.parse(message.data)));
eventSource.addEventListener("done", (message) => { eventSource.close(); onDone(JSON.parse(message.data)); });
eventSource.addEventListener("error", (message) => {
  if (message.data) { eventSource.close(); onFailed(JSON.parse(message.data)); }  // our terminal "error" frame
  // no data means a connection error: the browser reconnects by itself, sending Last-Event-ID
});
```

- **Use `addEventListener` for each type.** `onmessage` does **not** fire for
  frames that have an `event:` name, and every frame here has one.
- **Always `close()` on `done` / `error`.** Otherwise `EventSource` treats the
  closed response as a dropped connection and reconnects forever.
- **Our `error` frame and a connection error share the name `"error"`.** Tell
  them apart by `message.data`: only ours carries data.
- If connection errors continue for more than about 5 s, close the stream and
  switch to polling.

### Polling fallback — `/api/pipeline/status/<run_id>`

Built by the server from `runs[run_id]["frames"]`, for when SSE won't work:

```python
{
    "run_id":        "6f1c2a…",
    "state":         "running",                          # running | done | error
    "completed":     3,                                  # from the latest progress frame
    "total":         6,
    "stage_label":   "Matching companies to tickers",
    "last_message":  "Resolved 9 of 11 tickers",         # from the latest info frame
    "event_ids":     [],                                 # filled once state == "done"
    "exit_reason":   None,                               # set on an early-exit done
    "error_message": None,                               # set once state == "error"
}
```

Poll every 2 s and stop once `state` isn't `running`.

### A full run on the wire

Each frame is shown on one line for readability. On the wire, each is separate
`id:` / `event:` / `data:` lines followed by a blank line:

```
id: 0   event: progress  data: {"type":"progress","seq":0,"completed":0,"total":6,"stage":null,"stage_label":null}
id: 1   event: info      data: {"type":"info","seq":1,"message":"Searching news for the last 3 days","tag":"start"}
id: 2   event: progress  data: {"type":"progress","seq":2,"completed":1,"total":6,"stage":"NewsCollector","stage_label":"Collecting news"}
id: 3   event: info      data: {"type":"info","seq":3,"message":"Found 14 articles","tag":"stage_success"}
 …
id: 9   event: info      data: {"type":"info","seq":9,"message":"⚠️ No price data for XYZ, skipped","tag":"warning"}
 …
id: 14  event: progress  data: {"type":"progress","seq":14,"completed":6,"total":6,"stage":"EventWriter","stage_label":"Saving results"}
id: 15  event: done      data: {"type":"done","seq":15,"success":true,"event_ids":["2026-11-07-acme-recall"]}
```
