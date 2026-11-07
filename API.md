# 市场事件追踪 API

Ding 的 Flask 服务和 Xuan 的 React 前端共用此接口约定。开发时使用 Flask 的 5000 端口，前端通过 Vite 代理访问相对路径 `/api/...`。除 SSE 外，成功响应和错误响应均为 JSON。有请求体时发送 `Content-Type: application/json`。

## 接口一览

| 方法 | 路径 | JSON 请求体 | 成功响应体 |
|---|---|---|---|
| GET | `/api/health` | | `{"ok": true}` |
| GET | `/api/events` | | `[事件摘要]`，按 `event_date` 从新到旧 |
| GET | `/api/events/<event_id>` | | 事件详情，**原样返回** `Data_Cache/events/{event_id}.json` |
| POST | `/api/events/<event_id>/refresh` | | 调用 `refresh_event(event_id)`，返回新的详情 |
| GET | `/api/watchlist` | | `{"tickers": ["AAPL", "MSFT"]}` |
| POST | `/api/watchlist` | `{"ticker": "AAPL"}` | 同上（统一转大写、去重） |
| DELETE | `/api/watchlist/<ticker>` | | 同上 |
| GET | `/api/alerts` | | `[事件摘要 + "matched": [{"ticker", "relation", "car_pct", "is_significant"}]]` |
| GET | `/api/tracked` | | `[{"event_id", "ticker", "tracked_at"}]` |
| POST | `/api/tracked` | `{"event_id", "ticker"}` | 同上 |
| DELETE | `/api/tracked/<event_id>/<ticker>` | | 同上 |
| POST | `/api/pipeline/run` | `{"event_types": [...], "days_back": 3}` | `{"run_id": "..."}`；已有任务在跑时返回 409 |
| GET | `/api/pipeline/stream/<run_id>` | | SSE：`progress` / `info` / `done` / `error` frame（见下方 Pipeline 进度） |
| GET | `/api/pipeline/status/<run_id>` | | `{"state", "completed", "total", "stage_label", "last_message", "event_ids", "exit_reason", "error_message"}`（SSE 的备用方案） |

**事件摘要**（`/api/events` 和 `/api/alerts` 用，从详情文件里算出来）：

```json
{
  "event_id": "2026-10-21-acme-data-breach",
  "event_type": "breach",
  "headline": "string",
  "event_date": "YYYY-MM-DD",
  "status": "complete",
  "affected_count": 5,
  "top_impact": {"ticker": "ACME", "car_pct": -6.2, "is_significant": true},
  "touches_watchlist": true
}
```

- `top_impact`：`impacts` 里 `|car_pct|` 最大的那一个
- 错误统一返回 `{"error": "说明"}` 加对应状态码（400/404/409/500）

## 返回字段与空数据

- `event_type` 为 `merger`、`breach`、`recall`、`outage`、`lawsuit`、`regulation` 或 `other`。
- `status` 为 `complete` 或 `early`。`affected_count` 是 `impacts` 的条数。`touches_watchlist` 表示至少一个受影响的股票在自选股中。
- 摘要中的 `top_impact` 按 `study.car_pct` 的绝对值选择，返回值保留正负号。没有影响记录时返回 `null`。
- Alerts 只返回命中自选股的事件。`matched` 的每项形如 `{"ticker":"ACME","relation":"direct","car_pct":-6.2,"is_significant":true}`。其中 `relation` 为 `direct`、`competitor`、`supplier`、`customer` 或 `other`。
- 没有记录时，事件列表、Alerts 和追踪列表返回 `[]`，自选股返回 `{"tickers":[]}`。自选股和追踪的写接口返回更新后的完整列表，形状与各自的 GET 一致。
- 追踪列表的每项形如 `{"event_id":"2026-10-21-acme-data-breach","ticker":"ACME","tracked_at":"2026-11-07T12:00:00Z"}`。展示最新 CAR 时，用 `event_id` 获取详情，再按 `ticker` 找对应的 `study.car_pct`。

## 事件详情

详情和刷新接口都返回完整事件对象。字段源自 [Chen 的输出约定](todo_chen.md#4-output-shape-shared-contract-dont-change-it-after-020-without-telling-the-team)。`expected_direction` 为 `up`、`down` 或 `unclear`。`prediction_match` 为布尔值或 `null`，事件日前的 `daily[].car_pct` 为 `null`。百分比字段直接使用百分数的数值部分，例如 `-6.2` 显示为 `−6.2%`。

```json
{
  "event": {
    "event_id": "2026-10-21-acme-data-breach",
    "event_type": "breach",
    "headline": "string",
    "summary": "one sentence",
    "event_date": "2026-10-21",
    "source_url": "string"
  },
  "status": "complete",
  "generated_at": "2026-11-07T12:00:00Z",
  "impacts": [
    {
      "company_name": "string",
      "ticker": "ACME",
      "relation": "direct",
      "expected_direction": "down",
      "reason": "string",
      "prediction_match": true,
      "study": {
        "market_ticker": "^GSPC",
        "event_day": "2026-10-21",
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
          {"day": -10, "date": "2026-10-07", "actual_pct": 0.3, "expected_pct": 0.2, "abnormal_pct": 0.1,
           "cum_actual_pct": -0.5, "cum_expected_pct": -0.4, "car_pct": null}
        ]
      }
    }
  ]
}
```

## Pipeline 进度

启动接口返回 `{"run_id":"<uuid>"}`。已有任务运行时返回 HTTP 409。用该 ID 连接 SSE 接口，响应类型为 `text/event-stream`，每条消息用空行结束，且带 `id:`（`seq`，每次 run 从 0 开始的计数器）。前端用 `EventSource`，按事件名监听（`addEventListener`，不是 `onmessage`），并对 `event.data` 进行 JSON 解析。`Pipeline` 内部产出的 `progress` / `info` / `result` 事件由服务器转换为发到前端的 frame：`result` 本身**不会**到达前端，服务器把它翻译成 `done`（成功）或 `error`（失败）。

```text
id: 0
event: progress
data: {"type":"progress","seq":0,"completed":0,"total":6,"stage":null,"stage_label":null}

id: 1
event: info
data: {"type":"info","seq":1,"message":"Searching news for the last 3 days","tag":"start"}

id: 2
event: progress
data: {"type":"progress","seq":2,"completed":1,"total":6,"stage":"NewsCollector","stage_label":"Collecting news"}

id: 3
event: info
data: {"type":"info","seq":3,"message":"Found 14 articles","tag":"stage_success"}

 …

id: 14
event: progress
data: {"type":"progress","seq":14,"completed":6,"total":6,"stage":"EventWriter","stage_label":"Saving results"}

id: 15
event: done
data: {"type":"done","seq":15,"success":true,"event_ids":["2026-11-07-acme-recall"]}

```

- `progress`：`{type, seq, completed, total, stage, stage_label}`。`total` 固定为 6（pipeline 的阶段数）；`stage` 是模块的类名，`stage_label` 是该模块的 `label` 类属性（例如 `"Collecting news"`），用作前端进度条的说明文字。第一条 `progress` 的 `completed` 为 0、`stage`/`stage_label` 为 `null`。
- `info`：`{type, seq, message, tag}`。`tag` 为 `start`、`info`、`sub_stage_success`、`stage_success`、`sub_stage_fail` 或 `warning` 之一；未知 tag 按 `info` 处理。
- `done`：终止 frame。正常完成：`{type:"done", seq, success:true, event_ids:[...]}`。提前退出（例如没有新事件）：`{type:"done", seq, success:true, event_ids:[], exit_reason:"..."}`，`event_ids` 为 `[]`。收到 `done` 后关闭连接；若 `event_ids` 非空则刷新并高亮这些事件，若有 `exit_reason` 则展示为普通提示（不是错误）。
- `error`：终止 frame，`{type, seq, message}`。来源：pipeline 失败（`result.success` 为 `false`，`message` 取自 `error_message`）、请求参数被 `POST /api/pipeline/run` 拒绝（`400`，这种情况下 SSE 连接从未建立）、或后台线程崩溃且没有产出 `result`（`message: "Pipeline crashed"`）。收到 `error` 后关闭连接并展示 `message`。
- 每次 run 只有一个终止 frame（`done` 或 `error`），发出后服务器关闭该响应；连接断开/刷新可以重连并追上进度（`Last-Event-ID` 请求头）。
- 连接错误持续超过约 5 秒时，改为轮询 `/api/pipeline/status/<run_id>`，每 2 秒一次，直到 `state` 不再是 `running`。
- 状态响应形如 `{"run_id":"...","state":"running","completed":3,"total":6,"stage_label":"Matching companies to tickers","last_message":"Resolved 9 of 11 tickers","event_ids":[],"exit_reason":null,"error_message":null}`。`state` 为 `running`、`done` 或 `error`。`done` 时刷新列表并使用 `event_ids`/`exit_reason`，`error` 时展示 `error_message`。

## HTTP 错误

错误体统一为 `{"error":"说明"}`。无效请求返回 400，未知事件、任务或 API 路径返回 404，已有扫描任务时启动新任务返回 409，服务端异常返回 500。
