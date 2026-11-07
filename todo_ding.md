# Ding：Flask 服务器

**负责：** `Server/`
**原则：** 服务器**不做分析**，只负责三件事：调用 Chen 的 pipeline、读写 `Data_Cache/` 里的 JSON 文件、给前端提供 API；同时托管 Xuan 构建出来的 React SPA。
**今天不做：** 数据库、登录、部署、限流。

```
Server/
  app.py
  static_spa/      ← Xuan 的 vite build 输出到这里
Data_Cache/
  events/*.json    ← Chen 写，你只读
  watchlist.json   ← 你写
  tracked.json     ← 你写
```

---

## 0. 前 20 分钟

- [ ] 和 Chen、Xuan 确认第 2 节的 API
- [ ] `Server/app.py` 跑起来，`GET /api/health` 返回 `{"ok": true}`（端口 5000，和 Xuan 的 Vite 代理一致）
- [ ] 先用 Chen 提交的 `Data_Cache/events/mock_event.json` 当数据源，**不用等 pipeline**

## 1. 托管 SPA

- [ ] 参考 Job-finding-bot 的 `Deprecated/Flask_Server/app.py` 第 231–242 行（`index()` 和 `serve_spa()`）：`static_folder` 指向 `Server/static_spa`；文件存在就直接返回，否则一律返回 `index.html`（交给 React Router 处理）
- [ ] 确保 `/api/*` 路由优先于兜底路由；访问不存在的 `/api/...` 要返回 JSON 404，而不是 `index.html`

## 2. API

| 方法 | 路径 | 请求 | 返回 |
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
| GET | `/api/pipeline/stream/<run_id>` | | SSE：`progress` / `info` / `result` 事件 |
| GET | `/api/pipeline/status/<run_id>` | | `{"state": "running/done/error", "completed", "total", "last_message"}`（SSE 的备用方案） |

**事件摘要**（`/api/events` 和 `/api/alerts` 用，从详情文件里算出来）：

```json
{
  "event_id": "2026-10-21-acme-data-breach",
  "event_type": "breach",
  "headline": "string",
  "event_date": "YYYY-MM-DD",
  "status": "complete | early",
  "affected_count": 5,
  "top_impact": {"ticker": "ACME", "car_pct": -6.2, "is_significant": true},
  "touches_watchlist": true
}
```

- `top_impact`：`impacts` 里 `|car_pct|` 最大的那一个
- 错误统一返回 `{"error": "说明"}` 加对应状态码（400/404/409/500）
- 详情 JSON 的完整格式见 `todo_chen.md` 第 4 节

## 3. 运行 pipeline 并实时推送进度（SSE）

Chen 的 `stream_pipeline(params)` 是 **async generator**，而 Flask 的流式响应需要**同步**生成器，所以按下面的方式做：

- [ ] `POST /api/pipeline/run`：生成 `run_id`（`uuid4`），开一个后台 `threading.Thread`，线程里用 `asyncio.run()` 跑 `stream_pipeline`，把每个事件 `put` 进 `queue.Queue`，存在 `runs[run_id]` 里
- [ ] `GET /api/pipeline/stream/<run_id>`：用同步生成器从 queue 里取事件，经 `sse_format()` 输出（直接复制 Job-finding-bot `Django_Server/api/services/report_stream.py` 里的 `sse_format`）。设置 `mimetype="text/event-stream"`，响应头加 `Cache-Control: no-cache`
- [ ] 每个事件同时更新 `runs[run_id]["latest"]`，供 `/status` 轮询使用
- [ ] 同一时间只允许跑一个 run（演示够用，也避免撞 NewsAPI 每天 100 次的限额）
- [ ] 线程里出现异常时也要推送一个 `{"type": "error", "message": ...}`，再结束 stream

## 4. 存储

- [ ] `watchlist.json` / `tracked.json` 不存在时当作空列表
- [ ] 写文件时先写临时文件，再 `os.replace`，避免读到写了一半的文件
- [ ] 写操作加一个 `threading.Lock`（pipeline 线程和请求线程会同时访问）

## 5. Alerts 逻辑

- [ ] 遍历 `Data_Cache/events/*.json`：只要 `impacts` 里有任何 ticker 在 watchlist 中，就返回该事件，并在 `matched` 里列出命中的 ticker 及其 `relation`（区分 direct 和连带影响，演示时这一点很重要）

## 里程碑

| 时间 | 完成 |
|---|---|
| 0:20 | `/api/health` 可用，API 已确认 |
| 1:30 | 第 2 节除 pipeline 以外的接口全部能用 mock 数据返回；SPA 托管可用 |
| 2:30 | 接入 Chen 的 `stream_pipeline` 和 `refresh_event` → **三人联调** |
| 3:30–4:45 | 修联调问题；提前录制演示数据；确认 `npm run build` 之后只启动 Flask 就能跑完整演示 |
| 4:45 | 功能冻结 |

**最后检查：** 断网（或 yfinance 不可用）的情况下，打开两个演示事件也能正常显示（依赖 Chen 的价格缓存）。
