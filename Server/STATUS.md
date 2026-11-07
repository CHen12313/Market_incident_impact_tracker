# Server 实现状态与待解决问题

更新日期：2026-11-07。此说明基于当前 server 工作区；实现完成不代表已经通过真实 Pipeline 和 React 前端联调。

## 已完成的实现

| 文件 | 已实现内容 |
|---|---|
| `Server/app.py` | Flask 应用与 5000 端口启动入口；health、事件摘要/详情/刷新、自选股、Alerts、追踪、扫描启动/状态/SSE 接口；统一 JSON 错误 |
| `Server/app.py` | 自选股代码规范化及去重，追踪关系去重；自选股和追踪记录以临时文件加 `os.replace` 原子保存，进程内锁保护读改写 |
| `Server/app.py` | 后台线程运行 async generator，同一进程只允许一个扫描；追加保存 SSE 帧、序号、Last-Event-ID 重放、15 秒心跳和状态轮询；将 Pipeline result 转成客户端 done/error |
| `Server/app.py` | 托管 `Server/static_spa/`；页面路由回退到 index.html，未知 API 返回 JSON 404；无前端构建时页面返回 JSON 404 |
| `Server/seed_mock.py` | 从 `Pipeline/Mock_Event/` 复制两个上游 mock 到 `Data_Cache/events/`，不覆盖已有文件 |
| `tests/test_server.py` | 5 项 unittest，使用临时目录和假 Pipeline，不调用新闻、LLM 或价格服务 |
| `requirements.txt`、`.gitignore` | 添加 Flask 依赖及本地环境、自选股和追踪状态的忽略规则 |

启动、准备 mock 和测试命令见 [README](README.md)。服务器只读取事件文件，不承担分析计算。刷新接口委托 Pipeline 执行并返回结果。

## 已验证的范围

2026-11-07 执行 `.venv/bin/python -m unittest discover -s tests -v`，5 项全部通过：

- 空列表、health、SPA 假构建文件与未知 API 路径。
- mock 事件详情、摘要、Alerts、自选股、追踪和注入刷新函数。
- 无效请求参数与 JSON。
- 扫描互斥、完成后多次读取 SSE、Last-Event-ID 重放、状态轮询。
- 无结果提前退出、Pipeline 返回失败、抛异常及未返回终态时的处理。

这些测试不是浏览器端到端测试，也不能证明真实分析、真实前端或价格缓存已可用。

## 当前问题与交接事项

| 优先级 | 问题及影响 | 下一步 / 负责边界 |
|---|---|---|
| P0 | 当前缺少 `Pipeline/main.py`。扫描启动后会以 Pipeline crashed 结束，刷新返回 500；缓存读取仍可使用 | Chen 提供 async generator `stream_pipeline(params)` 与同步 `refresh_event(event_id)`；Ding 核对返回结构并联调 |
| P0 | 当前缺少 `Frontend/` 和 `Server/static_spa/` 构建产物，无法完成真实页面验收 | Xuan 提交前端并输出构建产物；Ding 验证仅启动 Flask 时页面和 API 均可用 |
| P0 | `todo_xuan.md` 写收到 result 后刷新，但数据契约及服务器发送的是 done/error | 前端以 `DATA_CONTRACT.md` 为准，监听命名事件，终态关闭连接；不要等待 result |
| P1 | `API.md` 接口表未列出 `GET /api/pipeline/stream/<run_id>` | 补充接口表；当前完整协议见 `DATA_CONTRACT.md` |
| P1 | 数据契约称 mock 已提交在 Data_Cache/events，实际已提交来源为 Pipeline/Mock_Event；契约引用的 scripts/make_mock_event.py 当前不存在 | 当前使用 seed_mock 准备数据；生成器与契约路径由 Chen 核对，避免另写一套生成逻辑 |
| P1 | 真实价格缓存、两个真实演示事件和断网完整演示尚未验证 | 等 Chen 提供事件及价格缓存、Xuan 提供构建后联合验收；mock API 可用不能代替此验收 |
| P1 | `.venv` 仍有文件被 Git 跟踪，新增忽略规则不会取消已有跟踪 | 此清理已在 Chen 的 TODO 中，统一由其处理以避免重复修改 |
| P2 | todo_ding.md 前面的历史清单仍未勾选，且 queue 方案已被追加帧记录替代 | 以本文件、实际代码和末尾实现进展为当前状态；后续整理历史清单 |

## 运行限制与测试缺口

- 仅支持演示用单进程：扫描状态、互斥和存储锁不跨进程；扫描记录重启后消失。
- 所有 run 和帧保留在内存，尚无清理机制，长时间持续扫描会增加内存占用。
- 事件读取依赖上游遵守契约。损坏 JSON、空 impacts 或缺少必要字段可能导致事件列表/Alerts 返回 500；当前没有逐文件隔离或契约校验。
- 现有测试未覆盖扫描进行时真实断线恢复、并发持久化、重建应用后的恢复、真实浏览器心跳行为、无 SPA 构建及真实刷新失败等完整场景。
- 服务器存储锁只保护自身的自选股与追踪读改写；Pipeline 必须自行保证事件文件原子写入。

## 下一步验收顺序

1. 在 tests 中补充断线恢复、持久化和失败路径测试，继续使用临时目录与注入 Pipeline。
2. 增加只读事件契约验收，检查两个 mock 及后续真实事件；不修改上游数据或分析算法。
3. 对接真实 Pipeline，验证成功、无新事件、失败、刷新及扫描互斥。
4. 接入前端构建，验证 Alerts → 详情 → 追踪、扫描进度和轮询回退。
5. 使用真实缓存完成断网演示，再冻结功能。

本次 server 提交不包含 Data_Cache/events 下的本地 mock 副本；可通过 seed_mock 重建。未修改 Pipeline、前端代码或公共数据字段。
