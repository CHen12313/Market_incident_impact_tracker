# Market Aftermath · 3 分钟 Demo

**演示主线**：用施耐德电气收购 PTC 的案例，展示如何从自选股发现相关事件、理解两只股票的表现差异，并保存一条记录供后续查看。

**预计时长**：约 2 分 55 秒，包含页面切换。英文引号内是现场口播，中文是操作和展示提示。

## 开场前准备

- **Alerts**：演示用自选股只放 **PTC** 和 **SU.PA**。确认 **Watchlist impact overview** 显示同一条收购新闻的两根横条，**PTC +33.4%**、**SU.PA −15.1%**。开场前确认 **GOOGL** 尚未加入自选股，并在 **All events** 确认 Alphabet 财报和入股 Qualcomm 两条事件都已有 GOOGL 分析。主页停在能看到自选股和影响图的位置。
- **Tracked**：如果施耐德收购事件的 **PTC** 已被保存，在 **Tracked** 点该条记录的 **Untrack PTC**。PTC 会继续留在主页自选股，影响图也会保留 PTC 横条。回到主页点开 PTC 横条，确认详情按钮显示 **Track PTC**，再回主页等待开场。
- **浏览器**：用一个标签页打开 **Market Aftermath**，停在 **Alerts**。提前确认扫描可启动、施耐德案例可打开且已有缓存行情。演示中用顶部导航切换页面，扫描状态会保留在当前标签页。

## 现场流程

| 时间 | 操作流程 | 英文讲述 | 这一步展示什么 |
|---|---|---|---|
| **0:00–0:30** | 停在 **Alerts**。提到两家公司时，指向影响图的两根横条。切到 **All events** 点击 **Scan latest news**，看到进度后切回主页。 | “Hi everyone. Imagine you follow two companies, and one morning you find out that one is buying the other. They’re in the same headline, but their shares can react very differently. Which one moved more than you’d normally expect? That’s what Market Aftermath helps answer. I’ll start a fresh news scan, then show you one example.” | 用具体问题引出目标用户和用途，同时启动实时扫描。 |
| **0:30–0:55** | 指出同一事件的 **PTC +33.4%**、**SU.PA −15.1%**，再指向观察窗口和行情截止日期。 | “Schneider Electric announced a deal to buy PTC. Both companies are on my watchlist. In the period shown here, PTC performed about 33 percentage points above its market-based expectation. Schneider performed about 15 points below its own.” | 展示一条新闻如何关联交易双方，以及主页如何让用户快速看到表现差异。 |
| **0:55–1:35** | 点击 **PTC** 横条。指向原文链接、事件日竖线、蓝色实际收益线和虚线预期收益，再切换到 **SU.PA**。 | “Here’s the news source and the announcement day. The blue line shows the stock’s performance. The dashed line shows what our model expected, based on how the stock normally moved with its market before the announcement. From the event day onward, the gap is the cumulative abnormal return. Other news may also have affected the stock.” | 展示来源可追溯、市场基准如何计算，以及异常收益的解释边界。 |
| **1:35–2:00** | 切回 **PTC**，点击 **Track PTC**。打开顶部 **Tracked**，指向刚出现的记录。 | “I can save PTC for this specific event. It’s now in my follow-up list. The next time I open the app, it refreshes saved event analyses in the background.” | 展示如何保存事件与股票的组合。重新打开或刷新网站时，后台会用可用的日收盘价重算已追踪事件，分析窗口截至事件后第 10 个交易日。现场无需重新加载页面。 |
| **2:00–2:30** | 回到 **Alerts**，在 **Your watchlist** 输入 **GOOGL**，点 **Add**。等影响图刷新，指出财报 **−5.2%** 和入股 Qualcomm **+0.6% · Early**，并对照两条记录的观察窗口。 | “Let’s add Alphabet to the watchlist. Now we see two stories for the same stock. It was about five points below the model’s expectation after earnings. For the Qualcomm investment, we only have one trading day, so that small positive move is an early reading.” | 展示添加一只股票后主页会自动更新；同一只股票可以关联多条新闻，比较时要看各自的观察窗口。 |
| **2:30–2:55** | 用顶部导航回到 **All events**，查看开场时启动的那次扫描。指向当前进度或新增与更新计数，然后收尾。 | **已完成：** “The scan shows how many events were added and how many existing ones were updated. A result marked Early has only a short trading window so far.” **仍在运行：** “The scan kept running while we moved between pages. We can see its current stage here.” **收尾：** “This lets me find news about my stocks, see how unusual the price moves were, and save the stories I want to follow.” | 展示切换页面后仍能看到同一次扫描的进度或结果，并区分新增与更新。 |

## 现场备选

- **新增为零**：指向实际的 **new / updated** 计数。英文可说 “This run added no new events. It shows separately whether any existing analyses were updated.”
- **扫描失败**：指向失败提示，然后用已加载的施耐德案例继续。英文可说 “The live scan couldn’t complete, so I’ll show the analysis we already have for this event.”
- **时间不足**：添加 GOOGL 后只指出新增的两条记录和 **Early** 标签，最后用一句话带过扫描状态。
