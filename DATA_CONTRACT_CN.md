# 数据契约

本文档定义应用三个部分之间所有跨边界传递的数据：pipeline（`Pipeline/`，Chen）、
Flask 服务器（`Server/`，Ding）和 React SPA（`Frontend/`，Xuan）。每条边界对应一份契约，共三份：

```
Pipeline ──Event File Contract──────────▶ Data_Cache/events/*.json ──原样返回──▶ Frontend
Pipeline ──Pipeline Status Event Protocol──▶ Server ──Client Stream Frame Protocol──▶ Frontend
```

**版本 1**，0:20 冻结。任何改动都要先通知三个人，再在这里把版本号加一。
英文版是 [DATA_CONTRACT.md](DATA_CONTRACT.md)，两份内容一致，有冲突以英文版为准。
完整的事件文件示例：`Data_Cache/events/2026-10-20-mock-nimbus-cloud-outage.json`。

## 目录

- [Event File Contract — pipeline → 服务器 → 前端](#event-file-contract--pipeline--服务器--前端)
  - [约定](#约定)
  - [完整的事件文件](#完整的事件文件)
  - [`event` — 发生了什么](#event--发生了什么)
  - [`impacts` — 谁受到了影响](#impacts--谁受到了影响)
  - [`study` — 事件研究结果](#study--事件研究结果)
  - [`daily` — 图表用的逐日数据](#daily--图表用的逐日数据)
  - [`prediction_match` / `verdict_text` — 通俗解读层](#prediction_match--verdict_text--通俗解读层)
  - [`status` — complete 还是 early](#status--complete-还是-early)
  - [不变式](#不变式)
  - [Mock 文件](#mock-文件)
- [事件摘要 — 服务器生成的列表项](#事件摘要--服务器生成的列表项)
- [`stream_pipeline` — 输入与结果](#stream_pipeline--输入与结果)
  - [`pipeline_params` — `stream_pipeline` 的输入](#pipeline_params--stream_pipeline-的输入)
  - [`stream_pipeline` 的结果格式](#stream_pipeline-的结果格式)
- [Pipeline Status Event Protocol — pipeline → 服务器的状态事件](#pipeline-status-event-protocol--pipeline--服务器的状态事件)
- [Client Stream Frame Protocol — 服务器 → 前端的 SSE frame](#client-stream-frame-protocol--服务器--前端的-sse-frame)
  - [线上格式](#线上格式)
  - [Frame 类型](#frame-类型)
  - [从 Pipeline Status Event Protocol 的转换](#从-pipeline-status-event-protocol-的转换)
  - [服务器行为 — 重放与重连](#服务器行为--重放与重连)
  - [客户端规则](#客户端规则)
  - [轮询备用 — `/api/pipeline/status/<run_id>`](#轮询备用--apipipelinestatusrun_id)
  - [一次完整运行的线上数据](#一次完整运行的线上数据)

## Event File Contract — pipeline → 服务器 → 前端

每个检测到的事件对应一个 JSON 文件，路径为 `Data_Cache/events/{event_id}.json`。
文件名永远等于 `event_id + ".json"`，所以服务器可以把 `GET /api/events/<event_id>`
直接映射到文件路径，不需要额外的索引。

**只有** pipeline 的最后一个阶段 `EventWriter` 会写这个文件：先写临时文件，再
`os.replace`，所以服务器永远不会读到写了一半的文件。用户点击 Refresh 或 Track 时，
`refresh_event(event_id)` 会原地重写它。服务器**只读**这些文件并原样返回；前端直接
渲染字段，自己不做任何计算。屏幕上的每个数字都只在 pipeline 里算一次。

pipeline 按阶段构建它的过程（和 Job-finding-bot 的 Generator 一样，用同一个 `data` dict）：

```
NewsCollector        adds    articles
EventExtractor       adds    events                  # LLM，response_format json_object；不合法的事件直接丢弃
TickerResolver       mutates events                  # 填入 ticker；找不到 ticker 的公司丢弃
EventStudyRunner     adds    impacts                 # 每家公司做一次研究；研究失败的公司丢弃
PredictionChecker    mutates impacts                 # 加上 prediction_match、verdict_text
EventWriter          writes  Data_Cache/events/{event_id}.json，adds event_ids
```

共 6 个阶段。`progress` 事件用这个数作分母，所以它必须和 pipeline builder 保持一致。

### 约定

- **百分比的单位是百分比。** `-6.2` 表示 −6.2%，保留 2 位小数。
- **收益是简单日收益，累计值是直接相加**，不做复利。这是事件研究的标准做法，
  也正因为如此，`car_pct = raw − expected` 才能严格成立。
- **`day`** 是相对事件的交易日序号。第 0 天是 `event_date` 当天或之后的第一个交易日，
  因为新闻常常在收盘后或周末发布。
- **日期**是 `YYYY-MM-DD` 格式的交易所当地交易日。`generated_at` 是 ISO-8601 UTC（`2026-11-07T11:02:13Z`）。
- **每个 key 都一定存在。** 只有下文注明的字段才可能是 `null`。

### 完整的事件文件

下面以 `EventWriter` dump 出的 Python dict 形式展示；文件里的 `True`/`False`/`None`
对应 `true`/`false`/`null`。数值取自 mock 事件：

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
    "status":       "complete",                     # "complete" | "early"，见 "status"
    "generated_at": "2026-11-07T11:02:13Z",
    "impacts": [                                    # 直接影响在前，连带影响按 abs(car_pct) 从大到小；不会为空
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
                    # ... 每个交易日一行 ...
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
        # ... 连带影响的公司，结构相同 ...
    ],
}
```

### `event` — 发生了什么

由 `EventExtractor`（LLM）根据同一新闻事件的一篇或多篇文章生成，之后所有阶段都不会改动它。

```python
{
    "event_id":   "2026-10-21-acme-data-breach",  # ^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$ — event_date + 简短 slug；同时也是文件名
    "event_type": "breach",                       # merger | breach | recall | outage | lawsuit | regulation | other
    "headline":   "...",                          # 原文标题，或 LLM 改写的一行标题
    "summary":    "...",                          # 一句通俗英文；显示在标题下方
    "event_date": "2026-10-21",                   # 新闻发布日期，可能是周末；第 0 天由它推出
    "source_url": "https://...",                  # 原文链接；原样复制，绝不由 LLM 生成
}
```

### `impacts` — 谁受到了影响

LLM 关联到这个事件的每家公司各占一项：新闻里直接提到的公司，加上最多 4 家连带影响的公司。
由 `TickerResolver` 和 `EventStudyRunner` 构建，`PredictionChecker` 补全。排序规则：
`direct` 在前，之后的连带影响公司按 `abs(study.car_pct)` 从大到小排，前端按顺序渲染即可。

```python
{
    "company_name":       "Stratus Systems",
    "ticker":             "STRS",            # Yahoo 格式："AAPL"、"TSCO.L"、"ASML.AS"；先查 DEMO_TICKER_OVERRIDES，再用 get_company_symbol()
    "relation":           "competitor",      # direct | competitor | supplier | customer | other
    "expected_direction": "up",              # LLM 的预测，在看价格之前就做出：up | down | unclear
    "reason":             "Main cloud competitor; likely to win customers looking for a backup provider.",  # 一句话，LLM 生成
    "prediction_match":   True,              # 见 "prediction_match / verdict_text"
    "study":              {...},             # 见 "study"；不会是 None
}
```

找不到 ticker 的公司由 `TickerResolver` 丢弃。研究失败的公司（没有价格数据，或历史数据不够估计窗口）由
`EventStudyRunner` 丢弃，并发出一条带 `tag: "warning"` 的 `info` 事件说明是哪家公司。
如果一个事件最后一个 impact 都没有，`EventWriter` 就不为它写文件。

### `study` — 事件研究结果

由 `Pipeline/event_study.py` 里的 `run_event_study(ticker, event_date, days_after=10)` 生成。
市场模型用第 −120 到 −10 个交易日拟合，所以新闻本身不会混进"正常走势"的估计里。

```python
{
    "market_ticker":       "^GSPC",       # 美股用 ^GSPC，.L 用 ^FTSE，.PA/.DE/.AS 用 ^STOXX50E
    "event_day":           "2026-10-20",  # 第 0 天的日期（event_date 当天或之后的第一个交易日）
    "days_after":          10,            # 实际包含的事件后交易日数：min(10, 已有天数)；决定 "status"
    "beta":                1.23,          # 第 -120..-10 天股票对大盘的斜率 —— "平时跟大盘跟得有多紧"
    "raw_return_pct":      -11.76,        # 股票从第 0 天到第 days_after 天的涨跌（= daily[-1].cum_actual_pct）
    "market_return_pct":   -0.67,         # 大盘同期涨跌
    "expected_return_pct": -0.46,         # alpha + beta × 大盘 算出的预期涨跌（= daily[-1].cum_expected_pct）
    "car_pct":             -11.3,         # 累计异常收益：事件本身的影响 = 实际 - 预期
    "t_stat":              -3.9,          # car_pct / (残差标准差 × sqrt(days_after + 1))
    "is_significant":      True,          # abs(t_stat) >= 2
    "verdict_text":        "...",         # 见 "prediction_match / verdict_text"
    "daily":               [...],         # 见 "daily"
}
```

### `daily` — 图表用的逐日数据

从第 −10 天到第 `days_after` 天，每个交易日一行，按顺序排列，这样图表既能显示事件前 10 天的平静期，
也能显示事件后的反应。前端直接以 `day` 为 x 轴，画 `cum_actual_pct`、`cum_expected_pct` 和 `car_pct`。

```python
{
    "day":              0,             # 交易日序号；0 = event_day
    "date":             "2026-10-20",
    "actual_pct":       -8.71,         # 股票当天收益
    "expected_pct":     -0.26,         # 当天 alpha + beta × 大盘收益
    "abnormal_pct":     -8.45,         # actual - expected，四舍五入前计算
    "cum_actual_pct":   -8.71,         # actual_pct 的累加，以第 -1 天为 0 重新起算
    "cum_expected_pct": -0.26,         # expected_pct 的累加，以第 -1 天为 0 重新起算
    "car_pct":          -8.45,         # 从第 0 天起 abnormal_pct 的累加；第 0 天之前为 None
}
```

以第 −1 天为 0 重新起算，所以图上每条线都在事件前一刻从 0 出发：之后发生的一切就是市场的反应。

### `prediction_match` / `verdict_text` — 通俗解读层

两者都由 `PredictionChecker` 写入，这样前端永远不需要自己判断一个数字是什么意思。

`prediction_match` 对比 LLM 的 `expected_direction` 和市场的实际表现：

```python
True    # 显著，且 car_pct 的正负与 expected_direction 一致
False   # 显著，但正负相反
None    # 不显著，或 expected_direction == "unclear" —— 无从验证
```

`verdict_text` 是一句话，前端原样显示，只有两种形式：

```python
# is_significant == True
"Fell 11.3% more than the market explains over 10 trading days (t = -3.9): very unlikely to be noise."
"Rose 8.2% more than the market explains over 10 trading days (t = 3.1): very unlikely to be noise."

# is_significant == False
"Moved roughly in line with the market: no clear effect from this event (t = 0.8)."
```

### `status` — complete 还是 early

```python
"complete"   # days_after >= 5
"early"      # days_after < 5 —— 今天或昨天的新闻；前端显示 "Early, still tracking" 标签
```

同一个文件里的所有 impact 都用相同的天数做研究，所以 `status` 属于整个事件，而不是单个公司。

### 不变式

`EventWriter` 写文件前会 assert 下面每一条（直接复制 `scripts/make_mock_event.py` 里的
`check_contract_invariants()`），所以前端可以放心依赖，不用自己检查：

1. `daily[0].day == -10`，`daily[-1].day == days_after`
2. 第 −1 天那一行 `cum_actual_pct == 0`，`cum_expected_pct == 0`
3. `daily[-1].car_pct == study.car_pct`，且 `car_pct ≈ raw_return_pct − expected_return_pct`（±0.05，四舍五入误差）
4. `abnormal_pct ≈ actual_pct − expected_pct`（±0.02，四舍五入误差）
5. `study.event_day` 等于第 0 天那一行的 `date`
6. 当且仅当 `days_after < 5` 时 `status == "early"`

### Mock 文件

`Data_Cache/events/` 里提交了两个 mock：

```
2026-10-20-mock-nimbus-cloud-outage.json         # complete，事件后 10 天；覆盖所有界面状态
2026-10-20-mock-nimbus-cloud-outage-early.json   # early，事件后 3 天；用来测试标签
```

两个文件合起来覆盖了：显著下跌、显著上涨、不显著，以及 `prediction_match` 为 `True` / `False` / `None`。
它们都由 `python3 scripts/make_mock_event.py [--days-after 3]` 生成，用的是和 `run_event_study()`
相同的计算和相同的不变式检查，只是价格是模拟的。Mock 的 `event_id` 里带 `-mock-`，标题以 `[MOCK]`
开头。**演示前删除这两个文件。**

## 事件摘要 — 服务器生成的列表项

`GET /api/events` 和 `GET /api/alerts` 不返回完整的事件文件（每个文件有 4 × 21 行逐日数据），
而是由服务器为每个文件生成一条摘要：

```python
{
    "event_id":         "2026-10-20-mock-nimbus-cloud-outage",
    "event_type":       "outage",
    "headline":         "...",
    "event_date":       "2026-10-20",
    "status":           "complete",
    "affected_count":   4,                                                     # len(impacts)
    "top_impact":       {"ticker": "NMBS", "car_pct": -11.3, "is_significant": True},  # abs(car_pct) 最大的那个 impact
    "touches_watchlist": True,                                                 # impacts[].ticker 中有任何一个在 watchlist.json 里
}
```

`/api/alerts` 只返回 `touches_watchlist: True` 的摘要，并且每条多一个 key，列出命中的 watchlist 股票：

```python
"matched": [
    {"ticker": "NMBS", "relation": "direct",     "car_pct": -11.3, "is_significant": True},
    {"ticker": "STRS", "relation": "competitor", "car_pct": 8.18,  "is_significant": True},
]
```

两个列表都按 `event_date` 从新到旧排序。

## `stream_pipeline` — 输入与结果

### `pipeline_params` — `stream_pipeline` 的输入

由服务器根据 `POST /api/pipeline/run` 的请求体构建。比 Job-finding-bot 的 `generator_params`
简单得多：没有用户、额度、CV 和 `seen_jobs_dict`。

```python
{
    "event_types": ["breach", "recall", "outage"],  # 可选；默认为除 "other" 以外的所有 event_type
    "days_back":   3,                               # 可选，默认 3；NewsCollector 往前搜索几天
}
```

`run_id` 由服务器生成，**不会**传进来。pipeline 不需要它，因为服务器会给收到的每个事件打上标记（见
[服务器行为](#服务器行为--重放与重连)）。

### `stream_pipeline` 的结果格式

`stream_pipeline` 逐条 yield 状态事件，最后以且仅以一条 `result` 事件结束。结果有三种格式，而不是两种：
和 Job-finding-bot 一样，提前退出也是 `success: True`：

```python
# 成功 —— 至少写了一个事件文件
{"type": "result", "success": True, "event_ids": ["2026-11-07-acme-recall"], "exit_reason": None}

# 提前退出 —— 正常运行，但没有找到值得写的事件；仍然是 success: True
{"type": "result", "success": True, "event_ids": [], "exit_reason": "No new events found"}

# 失败 —— 某个模块抛出了异常
{"type": "result", "success": False, "error_message": "❌ NewsAPI returned 401 for every key"}
```

`event_ids` 只包含本次运行写入或重写的文件，而不是 `Data_Cache/events/` 里的所有文件。

## Pipeline Status Event Protocol — pipeline → 服务器的状态事件

和 Job-finding-bot 的 Generator Status Event Protocol 是同一套协议：模块调用
`self.emit_status(data, message=..., tag=...)`，`execute_pipeline` 发出 `progress`，
`stream_pipeline` 持有队列并按顺序 yield 所有事件。唯一的新增是 `progress` 上的
`stage` / `stage_label`，前端用它作为进度条的说明文字。

- `progress` — `{type, completed, total, stage, stage_label}`。由 `execute_pipeline` 发出：
  循环开始前一次（`completed: 0`，`stage: None`），之后每个阶段完成后一次。`stage` 是模块的类名，
  `stage_label` 是模块的 `label` 类属性：

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

- `info` — `{type, message, tag}`。在模块的 `run` 里通过 `PipelineModule.emit_status` 发出。
  `tag` 取值为 `"start"`、`"info"`、`"sub_stage_success"`、`"stage_success"`、`"sub_stage_fail"`、
  `"warning"`，前端为每种 tag 使用不同样式，未知的 tag 按 `"info"` 处理。警告（丢弃了某家公司、跳过了
  某篇文章）是带 `tag: "warning"` 的 `info` 事件，不是单独的类型：

  ```python
  {"type": "info", "message": "Found 14 articles", "tag": "stage_success"}
  {"type": "info", "message": "⚠️ No price data for XYZ, skipped", "tag": "warning"}
  ```

- `result` — 终止事件，每次运行有且只有一条，最后 yield。格式见
  [`stream_pipeline` 的结果格式](#stream_pipeline-的结果格式)。

顺序规则：第一条一定是 `completed: 0` 的 `progress`；`result` 之后不再有任何事件。

## Client Stream Frame Protocol — 服务器 → 前端的 SSE frame

这一层消费 Pipeline Status Event Protocol，并把它转换成下面的 SSE frame。由服务器负责：
运行 `stream_pipeline` 的后台线程，以及 stream 路由 `GET /api/pipeline/stream/<run_id>`。

**frame 不等于 run。** pipeline 运行在服务器持有的后台线程里，由 `POST /api/pipeline/run`
在任何 frame 产生之前就启动了。浏览器断开或刷新只是收不到 frame，run 本身会继续运行。
和 Job-finding-bot 不同的是，这里重连**可以**追上进度：服务器保存了这次 run 的所有 frame，
并会重放（见 [服务器行为](#服务器行为--重放与重连)）。

### 线上格式

每个 frame 的格式是：

```
id: <seq>
event: <type>
data: <json>

```

- `id` 就是 `seq`：每个 run 单独计数，从 0 开始，由服务器添加
- `event` 和 `data` 里的 `type` 相同
- `data` 是 frame dict 加上 `seq`，写成单行 JSON
- frame 以一个空行结尾

响应头：`Content-Type: text/event-stream`、`Cache-Control: no-cache`、`X-Accel-Buffering: no`。
15 秒没有发送任何内容时，服务器发送一行注释 `: ping` 加一个空行，防止空闲连接被断开。
未知的 `run_id` 返回 `404` 和 `{"error": "Unknown run_id"}`。

### Frame 类型

- `progress` — `{type, seq, completed, total, stage, stage_label}`。从 Pipeline Status Event
  Protocol 原样转发，加上 `seq`。
- `info` — `{type, seq, message, tag}`。原样转发，加上 `seq`。
- `done` — 终止 frame，有两种：
  - 正常完成：`{type: "done", seq, success: true, event_ids: [...]}`。前端：关闭 stream，
    刷新事件列表，并高亮 `event_ids` 里的事件。
  - 提前退出：`{type: "done", seq, success: true, event_ids: [], exit_reason}`。前端：关闭
    stream，用中性提示显示 `exit_reason`，不要当作错误。
- `error` — `{type, seq, message}`。终止 frame。来源：pipeline 失败（`result.success` 为
  false）；参数不合法（`POST /api/pipeline/run` 直接返回 `400`，根本不会产生 stream）；或者线程崩溃、
  没有产出 `result`（message 为 `"Pipeline crashed"`）。前端：关闭 stream，显示错误信息。

两条不变式：

- `result` 永远不会到达浏览器。它是 Pipeline Status Event Protocol 的终止类型，服务器会把它转换成
  `done` 或 `error`。
- 每次 run 有且只有一个终止 frame（`done` 或 `error`），发出后服务器立即关闭响应。

### 从 Pipeline Status Event Protocol 的转换

| Pipeline Status Event Protocol | Client Stream Frame Protocol |
|---|---|
| `progress` / `info` | 不变，加上 `seq` |
| `result`（成功，`event_ids` 非空） | `done` |
| `result`（成功，有 `exit_reason`） | 带 `exit_reason` 的 `done` |
| `result`（失败） | `error`，`message` = `error_message` |
| 后台线程抛出异常且没有 `result` | `error`，`"Pipeline crashed"` |

### 服务器行为 — 重放与重连

```python
runs[run_id] = {
    "frames": [...],                 # 这次 run 的所有 frame，按顺序；只追加，从不删除
    "state":  "running",             # running | done | error —— 追加终止 frame 时同时设置
}
```

- 后台线程每收到一条状态事件就做转换，加上 `seq = len(frames)` 后追加进去。从不删除任何 frame，
  所以任意多个客户端都可以读同一个 run。
- stream 路由的起点：请求头里有 `Last-Event-ID` 时从 `Last-Event-ID + 1` 开始（`EventSource`
  重连时浏览器会自动带上），否则从 0 开始。先重放已保存的 frame，再每 0.2 秒检查一次 `frames`
  有没有新的，发出终止 frame 后立即关闭响应。
- 同一时间只允许一个 run：有 run 处于 `running` 时，`POST /api/pipeline/run` 返回 `409`。
  演示够用，也能保护 NewsAPI 每天 100 次请求的额度。

### 客户端规则

和 Job-finding-bot 不同，这个 stream 是 `GET`（run 由另一个 `POST` 启动），不需要发送 CSRF
或 session，所以前端直接用浏览器的 `EventSource`，不需要手动读取 `response.body`：

```js
const eventSource = new EventSource(`/api/pipeline/stream/${runId}`);
eventSource.addEventListener("progress", (message) => setProgress(JSON.parse(message.data)));
eventSource.addEventListener("info", (message) => appendLog(JSON.parse(message.data)));
eventSource.addEventListener("done", (message) => { eventSource.close(); onDone(JSON.parse(message.data)); });
eventSource.addEventListener("error", (message) => {
  if (message.data) { eventSource.close(); onFailed(JSON.parse(message.data)); }  // 我们自己的终止 "error" frame
  // 没有 data 说明是连接错误：浏览器会自动带着 Last-Event-ID 重连
});
```

- **每种类型都要用 `addEventListener`。** 带 `event:` 名字的 frame **不会**触发 `onmessage`，
  而这里每个 frame 都带名字。
- **收到 `done` / `error` 一定要 `close()`。** 否则 `EventSource` 会把服务器关闭响应当作掉线，
  不停地重连。
- **我们的 `error` frame 和连接错误同名，都叫 `"error"`。** 用 `message.data` 区分：只有我们的
  frame 带 data。
- 连接错误持续超过约 5 秒，就关闭 stream，改为轮询。

### 轮询备用 — `/api/pipeline/status/<run_id>`

SSE 用不了时使用。服务器根据 `runs[run_id]["frames"]` 生成：

```python
{
    "run_id":        "6f1c2a…",
    "state":         "running",                          # running | done | error
    "completed":     3,                                  # 取自最新的 progress frame
    "total":         6,
    "stage_label":   "Matching companies to tickers",
    "last_message":  "Resolved 9 of 11 tickers",         # 取自最新的 info frame
    "event_ids":     [],                                 # state == "done" 后才有值
    "exit_reason":   None,                               # 提前退出的 done 时才有值
    "error_message": None,                               # state == "error" 后才有值
}
```

每 2 秒轮询一次，`state` 不再是 `running` 就停止。

### 一次完整运行的线上数据

为了方便阅读，每个 frame 写成一行。实际传输时，每个 frame 是分开的 `id:` / `event:` / `data:`
三行，后面跟一个空行：

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
