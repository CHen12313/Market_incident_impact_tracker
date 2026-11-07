# Xuan：React 前端（SPA）

**负责：** `Frontend/`
**技术：** Vite + React + react-router-dom + recharts。`npm run build` 的输出放到 `Server/static_spa`，由 Ding 的 Flask 托管。
**界面文字用英文**（给评审看）。
**评审原则：** 用户不是技术人员；**清晰胜过精美**。每一屏都要**先给结论，再给图**。

---

## 0. 前 20 分钟

- [ ] `npm create vite@latest Frontend -- --template react`，然后 `npm i react-router-dom recharts`
- [ ] 复制 Job-finding-bot 的 `Frontend/vite.config.js`（已经把 `/api` 代理到 Flask 的 5000 端口），并加上：
  ```js
  build: { outDir: '../Server/static_spa', emptyOutDir: true }
  ```
- [ ] `package.json` 里 `build` 只保留 `vite build`。**不要**照搬 Job-finding-bot 里的 SSR / prerender 那一段
- [ ] 把 Chen 提交的 `Data_Cache/events/mock_event.json` 复制到 `src/mock/`。在 `src/api.js` 里加一个 `USE_MOCK` 开关：先全部用 mock 开发，联调时再切换到真实 API

## 1. 页面

### 1. 首页 `/`：Alerts（演示从这里开始）

- [ ] Watchlist：输入框加按钮添加股票代码，已添加的显示为可删除的标签（`GET/POST/DELETE /api/watchlist`）
- [ ] 下方是 `GET /api/alerts` 返回的事件卡片：标题、日期、事件类型标签、**命中了你的哪只股票**（标出 direct 还是连带影响）、CAR、是否显著；`status: "early"` 时显示 "Early, still tracking" 标签
- [ ] 点击卡片进入详情页

### 2. `/events`：全部事件

- [ ] 事件列表（`GET /api/events`）
- [ ] "Scan latest news" 按钮 → `POST /api/pipeline/run` → 用 `EventSource('/api/pipeline/stream/' + run_id)` 显示进度条（`progress` 的 `completed / total`）和滚动消息（`info` 的 `message`）
- [ ] 收到 `result` 后刷新列表；如果 SSE 出问题，就每 2 秒轮询一次 `/api/pipeline/status/<run_id>`

### 3. `/events/:event_id`：事件详情（**核心演示页，花最多时间**）

- [ ] 顶部：标题、一句话摘要、日期、类型、原文链接
- [ ] 公司切换：直接受影响的公司放第一位，连带影响的公司带 `relation` 标签（competitor / supplier / customer）和一句 `reason`
- [ ] **结论句**：大字显示 `study.verdict_text`；显著下跌用红色，显著上涨用绿色，不显著用灰色
- [ ] **预测 vs 实际**：AI 预测的方向（↑/↓）对比实测结果；`prediction_match` 为 `true` 显示 ✓，`false` 显示 ✗，`null` 显示 "—"
- [ ] **图表**（recharts `LineChart`）：x 轴为 `daily[].day`（相对事件日的交易日），三条线：
  - `cum_actual_pct`：股票实际走势（实线）
  - `cum_expected_pct`：按大盘推算的预期走势（虚线）
  - `car_pct`：事件本身的影响（第 0 天之前为 `null`，不画）
  - 在第 0 天画一条竖线，标注 "event"（`ReferenceLine`）
- [ ] 指标卡：Stock move（`raw_return_pct`）、Market move（`market_return_pct`）、Beta、Expected、**Event impact（`car_pct`）**、t-stat
- [ ] 按钮："Track"（`POST /api/tracked`）、"Refresh"（`POST /api/events/<id>/refresh`，加载时显示 spinner）

### 4. `/tracked`（有时间再做）

- [ ] 已追踪的事件和股票列表，每行显示最新 CAR

## 2. 数据格式

- 请求参数、返回字段、错误和 SSE 均以 [API 说明](API.md) 为准。mock 数据也使用相同的返回格式。
- 详情页直接使用 API 返回的分析字段，前端不做分析计算。

## 3. 让非技术用户看得懂

- [ ] 每个术语加一个 tooltip，用一句话解释：
  - Event impact (CAR)："How much the stock moved because of this news, after removing the overall market's move."
  - Beta："How strongly this stock usually follows the market."
  - t-stat / Significant："Whether the move is bigger than this stock's normal day-to-day noise."
- [ ] 页面底部一行小字："Information about past price moves, not investment advice."
- [ ] 数字统一保留 1 位小数，带 +/− 号和 %

## 里程碑

| 时间 | 完成 |
|---|---|
| 0:20 | Vite 项目跑起来，代理配置好，mock 数据已放入 |
| 1:30 | 详情页用 mock 数据完整渲染（结论句、图表、指标卡、预测对比） |
| 2:30 | 切换到真实 API → **三人联调** |
| 3:30–4:45 | Alerts 页、pipeline 进度条、tooltip、细节打磨 |
| 4:45 | 功能冻结，`npm run build` 输出到 `Server/static_spa`，确认只启动 Flask 就能打开 |

**今天不做：** 登录、暗黑模式、手机适配、SSR。
