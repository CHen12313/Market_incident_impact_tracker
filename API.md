# 市场事件追踪 API

Flask 后端和 React 前端通过 `/api/...` 对接。本地开发时，Vite 将这些相对路径代理到 Flask 的 5000 端口。事件数据和扫描进度以 [DATA_CONTRACT.md](DATA_CONTRACT.md) 为准。

## 接口一览

| 方法 | 路径 | 请求参数 | 成功结果 |
|---|---|---|---|
| GET | `/api/health` | 无 | 服务健康状态（`ok` 为真） |
| GET | `/api/events` | 无 | 事件摘要列表 |
| GET | `/api/events/<event_id>` | 路径中的事件 ID | 完整事件详情 |
| POST | `/api/events/<event_id>/refresh` | 路径中的事件 ID | 刷新后的完整事件详情 |
| GET | `/api/watchlist` | 无 | 自选股列表（`tickers`） |
| POST | `/api/watchlist` | 请求体中的 `ticker` | 更新后的完整自选股列表 |
| DELETE | `/api/watchlist/<ticker>` | 路径中的股票代码 | 更新后的完整自选股列表 |
| GET | `/api/alerts` | 无 | 命中自选股的事件摘要列表 |
| GET | `/api/tracked` | 无 | 追踪记录列表 |
| POST | `/api/tracked` | 请求体中的 `event_id`、`ticker` | 更新后的完整追踪列表 |
| DELETE | `/api/tracked/<event_id>/<ticker>` | 路径中的事件 ID 和股票代码 | 更新后的完整追踪列表 |
| POST | `/api/pipeline/run` | 可选的 `event_types`、`days_back` | 本次扫描的 `run_id` |
| GET | `/api/pipeline/stream/<run_id>` | 路径中的扫描 ID | SSE：扫描进度与结果（见下方"扫描任务"） |
| GET | `/api/pipeline/status/<run_id>` | 路径中的扫描 ID | 扫描状态和结果 |

## 事件与追踪

- 事件列表和 Alerts 按 `event_date` 从新到旧排序。后端生成事件摘要，Alerts 额外提供命中的股票。字段定义见 [事件摘要](DATA_CONTRACT.md#event-summary--server-built-list-items)。
- 详情接口和刷新接口均返回完整事件。后端原样返回事件数据，前端直接使用已计算的数值。字段、单位和空值约定见 [事件文件契约](DATA_CONTRACT.md#event-file-contract--pipeline--server--frontend)。
- 后端将自选股代码统一转为大写并去重。没有记录时，事件、Alerts、自选股和追踪接口均返回各自的空列表。
- 每条追踪记录包含 `event_id`、`ticker` 和 UTC 时间 `tracked_at`。展示最新 CAR 时，前端用 `event_id` 获取详情，再按 `ticker` 读取对应的 `study.car_pct`。

## 扫描任务

- `event_types` 默认包含除 `other` 外的所有事件类型，`days_back` 默认是 3。后端同一时间只运行一个扫描任务。
- 前端用启动接口返回的 `run_id` 获取进度和结果。进度、结果以及前端处理规则见 [客户端进度协议](DATA_CONTRACT.md#client-stream-frame-protocol--server--frontend-sse-frames)和[状态查询](DATA_CONTRACT.md#polling-fallback--apipipelinestatusrun_id)。

## HTTP 错误

前端从 `error` 字段读取错误说明。无效请求返回 400，未知事件、任务或 API 路径返回 404，扫描运行中再次启动返回 409，服务端异常返回 500。
