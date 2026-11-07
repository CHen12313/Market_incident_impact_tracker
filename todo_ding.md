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

- [ ] 和 Chen、Xuan 确认 [API 说明](API.md) 中的接口约定
- [ ] `Server/app.py` 跑起来，`GET /api/health` 返回 `{"ok": true}`（端口 5000，和 Xuan 的 Vite 代理一致）
- [ ] 先用 Chen 提交的 `Data_Cache/events/mock_event.json` 当数据源，**不用等 pipeline**

## 1. 托管 SPA

- [ ] 参考 Job-finding-bot 的 `Deprecated/Flask_Server/app.py` 第 231–242 行（`index()` 和 `serve_spa()`）：`static_folder` 指向 `Server/static_spa`；文件存在就直接返回，否则一律返回 `index.html`（交给 React Router 处理）
- [ ] 确保 `/api/*` 路由优先于兜底路由；访问不存在的 `/api/...` 要返回 JSON 404，而不是 `index.html`

## 2. API

- [ ] 按 [API 说明](API.md) 实现并验证接口，包括返回结构、错误和 SSE。

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
