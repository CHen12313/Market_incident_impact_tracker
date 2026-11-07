# Flask server

从仓库根目录启动：

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m Server.app
```

服务监听 `http://127.0.0.1:5000`。Vite 开发代理指向该端口；将前端 build 输出到 `Server/static_spa/` 后，Flask 会托管静态文件和 React Router 路由。未构建前端时，API 仍可用，页面请求返回 JSON 404。

## 前端与数据

开发模式在另一个终端运行 `npm ci --prefix Frontend` 和 `npm run dev --prefix Frontend`。生产构建运行 `npm run build --prefix Frontend`，然后打开 Flask 的地址。前端默认使用真实 API。只运行前端演示时可设置 `VITE_USE_MOCK=true`。

`Data_Cache/events/` 已包含两个离线样例。自选股和追踪记录分别写入 `Data_Cache/watchlist.json`、`Data_Cache/tracked.json`。

## Pipeline 对接

真实扫描需要在仓库根目录的 `.env` 或环境变量中设置 `NEWS_API_KEY` 和 `OPENAI_API_KEY`。备用 NewsAPI 密钥和 `FINNHUB_API_KEY` 可选。价格优先读取 `Data_Cache/prices/` 的缓存，缺少所需数据时请求 Yahoo Finance。

Server 调用 `Pipeline.main.stream_pipeline(params)` 执行扫描，通过 SSE 或轮询返回进度。扫描成功后事件文件写入 `Data_Cache/events/`，前端刷新列表。事件详情中的 Refresh 重新计算已有股票的研究结果，Track 保存事件与股票的关联。

`create_app(config)` 支持 `DATA_CACHE`、`SPA_DIR`、`PIPELINE_STREAM`、`EVENT_REFRESH`，用于隔离测试和注入 pipeline。

SSE 使用追加帧记录，支持多个客户端和 `Last-Event-ID` 重放；扫描不随浏览器断线停止。运行记录保存在内存中，重启后消失。演示环境使用单进程服务，不能启动多个 worker，否则扫描互斥和文件锁不能跨进程生效。

## 验证

```sh
.venv/bin/python -m unittest discover -s tests -v
```

测试使用临时数据目录和可控的 async generator，不调用外部新闻、LLM 或价格 API。

历史联调记录见 [STATUS.md](STATUS.md)。
