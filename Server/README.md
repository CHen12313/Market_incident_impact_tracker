# Flask server

从仓库根目录启动：

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m Server.app
```

服务监听 `http://127.0.0.1:5000`。Vite 开发代理指向该端口；将前端 build 输出到 `Server/static_spa/` 后，Flask 会托管静态文件和 React Router 路由。未构建前端时，API 仍可用，页面请求返回 JSON 404。

## 离线 mock

当前上游 mock 位于 `Pipeline/Mock_Event/`。在根目录执行以下命令，将其复制到契约约定的数据目录（不覆盖已有文件）：

```sh
.venv/bin/python -m Server.seed_mock
```

这只是手动准备演示数据；服务器不会自动生成或修改事件文件。真实演示前应移除带 `-mock-` 的事件。自选股和追踪记录分别写入 `Data_Cache/watchlist.json`、`tracked.json`，缺失时返回空列表。

## Pipeline 对接

服务器在调用时加载 `Pipeline.main.stream_pipeline(params)` 和同步的 `Pipeline.main.refresh_event(event_id)`。这两个入口尚待 Chen 实现。缺失入口时，扫描通过 SSE/polling 返回 `Pipeline crashed`，刷新返回 HTTP 500；已缓存事件、Alerts 和追踪接口不受影响。

`create_app(config)` 支持 `DATA_CACHE`、`SPA_DIR`、`PIPELINE_STREAM`、`EVENT_REFRESH`，用于隔离测试和注入 pipeline。事件与 Alerts 返回 JSON 数组；追踪返回 JSON 数组；自选股返回 `{"tickers": [...]}`。追踪保存关联关系，刷新由单独的 refresh 接口触发。

SSE 使用追加帧记录，支持多个客户端和 `Last-Event-ID` 重放；扫描不随浏览器断线停止。运行记录保存在内存中，重启后消失。演示环境使用单进程服务，不能启动多个 worker，否则扫描互斥和文件锁不能跨进程生效。

## 验证

```sh
.venv/bin/python -m unittest discover -s tests -v
```

测试使用临时数据目录和可控的 async generator，不调用外部新闻、LLM 或价格 API。

## 实现状态与已知问题

已完成内容、验证范围和待联调事项见 [STATUS.md](STATUS.md)。
