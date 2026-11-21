# V0.1.0 验收记录

## 2026-11-21 Git 仓库根目录迁移

- 已核对原仓库全部 329 个 Git 元数据文件的 SHA-256，`git fsck --full` 完整性检查通过。迁移前的 `main` 提交为 `4d708cf`。
- 在 `SignalDesk` 中执行 `git rev-parse --show-toplevel` 返回项目目录，在 `Finance` 和同级插件目录执行均返回“非 Git 仓库”。两份 Pine 脚本与外层目录说明的 SHA-256 与迁移前一致。
- Git 索引包含原项目子树及两份 Git 配置，共 57 个文件。私密运行文件隔离测试通过，另用 `git check-ignore` 确认前端构建、虚拟环境、数据库等七个样例路径均被忽略。本次仅调整仓库范围，验证集中在 Git 与文件隔离。

## 2026-11-21 项目目录迁移

- 从 `Finance/SignalDesk/` 按锁文件离线重建 Python 环境，核对新旧 44 个已安装包的名称和版本一致。前端生产构建和 Ruff 检查通过。
- 原后台实例正常停止后，从 `Finance` 调用 `SignalDesk\Start-SignalDesk.cmd --background --port 8765` 恢复服务。新目录的 Python 进程已启动，`/api/health` 返回应用名 `SignalDesk`，首页返回 HTTP 200。
- 在当前 Windows 用户权限下运行全量 pytest，61 项通过，测试客户端报告 1 条弃用提示。沙箱内首次运行受 pytest 临时目录权限限制。
- 已核对两份 Pine 脚本与迁移前的 Git 版本一致。本轮未在 TradingView 中运行脚本，也未复测券商登录。

## 2026-11-21 长桥 OAuth 2.0

- **官方服务。** 本机客户端向长桥完成动态注册，客户端 ID 已保存在本机加密目录。真实授权请求携带 PKCE S256 及账户读取、自选股范围，长桥返回 HTTP 302，目标为官方授权确认页。真实账户的令牌兑换、持仓和自选同步、行情推送及到期续期待账户持有人登录后验证。
- **协议与 SDK。** 使用合成凭据测试注册复用、浏览器绑定、state 校验、单次回调、超时、授权失败保留旧凭据、并发续期、刷新令牌轮换与撤销。通过本地 HTTP 服务捕获实际 `longbridge 5.5.0` 的合成请求，验证 Bearer 请求头、区域路由及省略 HMAC 签名。Windows DPAPI 加密文件与设置返回值均通过隔离检查。
- **界面。** Edge 在 1440 × 810 演示工作区验收亮色、深色、默认 OAuth 选项和旧版三凭据表单。模拟授权站点在新标签页返回本机回调，结果页和原设置页均显示授权完成，过程中未发生页面脚本错误。
- **构建与回归。** 前端 TypeScript 检查及 Vite 生产构建通过，Ruff 通过，本机全量 pytest 61 项通过。测试收集时 Starlette 提示现有 TestClient 的 httpx 依赖将弃用。

## 2026-11-21 Windows 启动与停止脚本

- 在路径含空格和方括号的临时项目副本中，从其他工作目录调用 `Start-SignalDesk.cmd --background --port <空闲端口>`。首次启动完成 `uv sync --frozen`、`npm ci` 和前端生产构建，演示服务的 `/api/health` 返回 `SignalDesk`，随后 `Stop-SignalDesk.cmd` 正常退出。
- 在独立演示数据目录实测两个 CMD。其他程序占用端口时，启动返回退出码 1，原监听仍可连接。重复启动复用已有实例，连续停止两次均返回 0，原端口可立即重启。
- 新增回归覆盖服务就绪后才打开正确端口、等待停止超时、无界面服务完整退出及端口释放。隔离检出全量 56 项通过，共享工作区最终复跑 61 项通过，均有一条既有的 Starlette 弃用提示。Ruff 与 Git 私密文件隔离专项检查通过。
- 此次脚本验收使用后台托盘和无界面模式。浏览器打开动作通过测试替身核对目标 URL，未手动点验默认浏览器和托盘菜单。

## 2026-11-20 16:9 桌面紧凑排版与单行对齐修复

- **排版与文案收紧。** 针对 16:9 桌面视口（`1440×810`）中个股抬头、`采纳为计划价`、`全屏`、OHLC 均线行及右栏中枢价/锚点文本各自单独折行占用垂直空间的问题，调整 `.terminal-grid` 默认列宽至 `296px / 1fr / 372px`（为中栏释放 `+50px` 横向空间），收敛 `.stock-hero`（自选分组标签上限 2 个、持仓上限 1 个并以 `+N` 提示完整分组）、`.verdict-banner` 与 `.forecast-strip`、`.chart-toolbar`（`近3月..最新` / `MA/BOLL/净图` / `MACD/RSI/点位` + `全屏`）、`.ohlc-hud`（合并均线色块间距并收敛大成交量位数）、右栏 `.forecast-level-cell`（改为首行标题+价位、次行通栏副说明避免 3 行折断）、`.button.forecast-apply-btn` 紧凑高度与 `.rating-factors` 2×2 网格；同步修复 `signaldesk/forecast.py` 卖出锚点重复价位并精简防守依据。
- **实盘浏览器与自动检查（`1440×810` 企业简洁风亮色）。** 重启服务并重新构建生产包（`vite build` 6.13s，产出 `index-BYCPZQAs.js` / `index-BGQYuUa-.css`）后核对：
  - `.stock-hero` 总高 `60px`（报价与按钮同处单行）；`.verdict-badges` 两枚徽章同行并排；`.forecast-strip`（`买点`/`卖点`/`止损`/`盈亏比`/`采纳计划价`）单行无折行；`.chart-toolbar`（含 `全屏`）单行无折行；`.ohlc-hud` 单行且最右侧 `MA200 203.58` 距容器右边界留有 `10px` 余量无截断；`.chart-plot` 首屏高度达 `393px`。
  - 右栏 `买卖评级与点位预测` 标题与评级徽章单行对齐、三张价位卡严格 2 行（`距买点 -0.2% · 中枢 $141.74` 不再折行）、`采纳为计划价` 按钮高度 `29.2px`、四因子 2×2 网格清晰无截断；控制台 **0 errors**，全部 7 个资源/API 请求均返回 HTTP **200**。
  - CSS 字号正则检查全部 133 条 `font-size` 声明最小值为 `12.0px`；全量 pytest **53 项通过**，`ruff check signaldesk tests` 全通过，无私密/运行产物进入 Git 跟踪。
- **未验证项。** 同本轮此前说明（真实 Codex CLI 手动推理、长桥 App 同屏历史逐笔对账与 24 小时断网压测尚未实测）。

## 2026-11-20 买卖点位预测与 5 级综合评级

- **功能与架构变更。** 新增因果点位预测与 5 级评级引擎 `signaldesk/forecast.py`（`compute_forecast()`），并在 `signaldesk/service.py`（`Monitor.stock()` 与 `Monitor.snapshot()["summary"]` 聚合统计 `buy_rated` / `hold_rated` / `sell_rated`）与 `signaldesk/security.py`（`safe_snapshot()` 白名单透传脱敏 `rating`/`levels`）接入；前端新增 `frontend/src/StockInspector.tsx` 的「买卖评级与点位预测」卡片、中栏结论条 `forecast-strip` 点位速览、K 线工具栏 `预测点位` 虚线标注层、左侧列表 `买卖评级优先` 排序，以及一键「采纳为计划价」预填 `AllocationEditor`（由用户确认保存）。
- **自动化测试与构建。** 全量 pytest **53 项通过**（含新建 `tests/test_forecast.py` 5 个测试与 `tests/test_api.py` 的 `/api/bootstrap` + `/api/analysis/preview` 隐私/单调断言，存在 1 条既有的 Starlette httpx 兼容弃用提示）；`ruff check signaldesk tests` 全通过；`frontend` 下 `tsc -b` 与 `vite build`（Windows 沙箱外执行以绕过 Vite `realpath` `EPERM`）生产构建通过（4.93s，输出 `index-CVSb66da.js`、`index-9abtaCjD.css`）；样式字号正则检查确认 `frontend/src/style.css` 共 131 条 `font-size` 声明，最小值为 `12.0px`，无低于 `12px` 字号。
- **实盘看盘浏览器核对。** 重启本机无界面服务至最新构建后访问 `http://127.0.0.1:8765`（实盘只读模式，同步 92 只美股自选、自动忽略 44 只非美股），在 `1423×1269` 企业简洁风亮色桌面三栏视图核对通过：
  - 左侧支持切换 `买卖评级优先` 并按分数降序重排；对盈利为负或缺有效评级标的（如 `ANT`/`SPCX`）诚实回落显示 PE，其余标的显示 `建议买入`/`中性观望`/`谨慎减持`/`建议卖出` 等迷你评级。
  - 选中 `NVDA`（`$145.98 -3.30%`）：中栏显示 `● 暂缓观察` + `● 中性观望 48分` 与 `.forecast-strip`（买点 `$137.77 – $145.71`、卖点 `$163.76 – $195.41`、止损 `$129.86`、现价盈亏比 `1.10:1`），K 线工具栏开启 `预测点位` 后在图面右侧渲染对应虚线标注。
  - 右栏「综合研判」中「买卖评级与点位预测」卡片单行对齐标题、`置信度 低` 与 `● 中性观望 47.5分`，三条水平价位行卡、锚点依据、空头弱势风控护栏与四因子明细完整无横向溢出；点击「采纳为计划价」正确预填失效价 `129.86` 与目标价 `163.76` 并通过「取消」关闭未改写实盘计划；最终重载检查控制台 **0 errors**，全部 7 个资源/API 请求均返回 HTTP **200**。
- **未验证项。** 本轮未执行真实 Codex CLI 手动分析推理；未对照长桥 App 同屏历史分时/日线逐笔读数；未执行 24 小时断网与长时间挂机监控压测。

## 2026-11-20 桌面看盘重构、企业简洁风、自选同步与手动 Codex

- **功能与架构变更。** 重构前端为三栏桌面看盘工作台并采用「企业简洁风」默认亮色主题（`#f8fafc` 浅灰蓝画布 + 白卡 `1px #e5e7eb` 描边 + 单一企业蓝 `#1e40af`，最小字号 `12px`）；新增后端确定性 `verdict` 研判结论条与右栏三标签；新增 LongPort 只读自选同步（`LongPortFeed.watchlist` + `POST /api/watchlist/sync`）、本地收藏（`PUT /api/favorites/{symbol}`）；关闭事件自动触发 Codex（`CodexSettings.automatic = False` 并在 `Monitor.on_events()` 移除自动调用）。
- **自动化测试与构建。** 全量 pytest **47 项通过**（新增 API 收藏/自选同步、mock LongPort 自选分组合并与 `verdict`、Codex 默认纯手动及事件不自动触发测试）；`ruff check signaldesk tests` 全通过；`frontend` 目录下 `tsc -b` 与 `vite build` 生产构建通过（在 Windows 沙箱外执行以绕过 Vite `realpath` 的 `EPERM` 限制）；正则表达式核对 `frontend/src/style.css` 全部 115 处 `font-size` 声明最小值为 `12px`。
- **实盘自选同步与浏览器视觉核对。** 启动本机无界面服务（`127.0.0.1:8765`）并通过浏览器查看：实盘模式成功只读同步 LongPort 账号的 **92 只美股自选标的**（自动忽略 44 只非美股标的）与分组标签，展示美国国债 2Y/10Y 收益率及最新收盘价/涨跌幅；企业简洁风亮色主题下三栏卡片、状态圆点徽章、日线 K 线/成交量/MACD/RSI 图表以及「综合研判」「Codex 总结（含手动触发模式标记）」「提醒动态」标签页均渲染清晰，控制台 **0 errors**，网络请求全部 200。
- **未验证项。** 本轮未实际触发真实 Codex CLI 推理（因 Windows 查找 `codex.exe` 与 npm 全局 `codex.cmd` 差异，界面状态提示 `unavailable`）；未在实盘环境核对特定股票的历史长桥 App 同屏读数与 24 小时断网连续运行。

## 2026-11-20 长期计划与日线补数

- **长期计划。** 在独立 SQLite 演示库中用 Edge 保存 NVDA 失效价 135 美元、目标价 142 美元。演示日线在纽约时间 11 月 19 日 16:00 收于 142.80 美元，持仓列表显示“复核计划目标价”。分析预览显示收盘价高于目标价约 0.56%、高于失效价约 5.78%。刷新页面、重启服务后再次打开，两个计划价和目标价提示均可读回。
- **图表。** 在 1440 × 900 和 390 × 844 的浏览器窗口核对全屏日线，图面完整显示，标题可识别标的、来源及纽约收盘日期。两条水平线标出 135.00 和 142.00 美元。在三个月区间内向前拖动，定位至 8 月 5 日，再模拟定时刷新移除最早一根、增加最新一根日线，光标仍对应 8 月 5 日。本机截图见[全屏日线](../output/playwright/long-plan-chart-1120.png)和[持仓看板](../output/playwright/long-plan-dashboard-1120.png)。
- **日线恢复。** 用模拟行情源执行监控轮询，覆盖正常新增一个交易日、漏掉 12 个交易日、历史请求暂缺一根日线三种情况。出现断档后回补已收盘日线，缺失仍在时评分保持不可用，后续请求取回该记录后恢复。反复轮询同一批记录不会重复触发事件或通知。
- **自动检查。** 全量 pytest 41 项通过，有一条现有的 Starlette 测试客户端弃用提示。Ruff 和前端 TypeScript、Vite 生产构建通过。本轮使用演示库和模拟行情源，真实券商权限及连续运行仍待实盘核验。

## 2026-11-19 长期复核版本

**公开行情对账。** 以 SPY.US 在 2025-11-28 的常规时段、不复权历史日线为例，长桥返回开 680.86、高 683.665、低 680.50、收 683.39、成交量 49,973,521 股、成交额 34,098,587,619.881 美元。日线日期标记是纽约 00:00（05:00 UTC），当天提前于纽约 13:00（18:00 UTC）收盘。同一历史接口的 14 根常规时段 15 分钟线，末根收 683.34、合计成交 9,262,237 股。这里记录两个接口的实际差异，原因尚未获得供应商确认。长期工作台直接采用日线接口。[长桥历史 K 线接口](https://open.longportapp.com/docs/quote/pull/history-candlestick)

**本机复现。** `tests/test_long_research.py` 使用上述公开记录，按 SDK 的本机无时区时间输入，经转换、缓存、指标和图表序列化核对结果。另测收盘前排除、历史回补不覆盖已确认记录、缺交易日后的指标重新预热，以及旧混合仓的计划价归属。SDK 在输出方向调用本机 `fromtimestamp`；旧实盘缓存保留在原分区，重新连接后回补新分区。[锁定版本的 SDK 时间实现](https://github.com/longportapp/openapi/blob/v4.3.7/python/src/time.rs)

**宏观对账。** 实际读取财政部月度 XML。2025-11-28 的 2 年期为 3.47%、10 年期为 4.02%，期限利差 55 bp。之前第 21 个有效观测日为 2025-10-28，10 年期变动 +3 bp。测试还覆盖非正 PE、缺失与过期数据。该日期仅用于验收。[美国财政部 2025 年 11 月利率表](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve&field_tdr_date_value_month=202511)

真实账户的行情权限、长桥 App 同屏数值、连续监控和真实通知仍需在对应环境验收。

## v0.1.0 历史验收记录


核验日期：2026-10-28。环境：Windows、Python 3.12.9、Node.js 24.22.1；运行依赖以 `uv.lock`、`frontend/package-lock.json` 为准。全部样例、截图和测试持仓为合成数据。

## 已完成的验收

| 范围 | 结果与证据 |
|---|---|
| 自动化测试 | `python -m pytest -q`：**33 passed**，7.50秒。`ruff check signaldesk tests`：通过。测试覆盖完整窗口、缺失值、零方差、负窗口拒绝、已确认K线、日历/DST/提前收盘、断档重新预热、停牌、异常/过期/乱序报价。 |
| 独立数值 | 用独立循环/数组公式核对SMA、EMA、RSI、MACD及信号线、ATR、布林带和日线RVOL；核对融合权重、历史前缀与完整数据计算一致，未来记录不改变既有结果。 |
| 融合事件 | 覆盖同类指标归组后的维度确认、冷却跨重启、去重、机会流动性门控、下行风险继续提醒、关键价穿越、演示/实盘状态分离。首次加载建立基线。 |
| QQ官方通道 | HTTP模拟覆盖官方URL与鉴权、token缓存、401强制刷新、token端HTTP 200业务失败、主动权限不足、限流、平台消息回执、失败健康状态；持久队列最多3次尝试，重启不盲发未知结果。普通事件合并与重要风险优先通过测试。未向真实QQ目标发送测试消息。 |
| Codex | 使用本机已有CLI登录、模型和推理强度，**真实执行合成快照分析成功**，结果通过JSON Schema/Pydantic校验并展示于页面，重启后保留。180秒首次超时后，以600秒等待完成；默认已相应调整。另有自动预算/同股冷却、超时杀进程和环境变量隔离测试。演示模式不自动调用。 |
| 前端 | `npm run build`：TypeScript与Vite生产构建通过。真实Chromium验收1600×1100、1280×900、1024×768；明暗主题、长短线筛选、盘前/盘中图表、BOLL切换、分仓编辑取消、凭据向导及脱敏预览可用，无整页横向溢出。最终新会话console为0 errors/0 warnings，页面、JS、CSS、API请求全部来自127.0.0.1并返回200。 |
| Windows运行 | 已通过交付的 `Start-SignalDesk.cmd` 启动pythonw程序，API返回demo、8只示例资产、本地通知ready；修复并回归验证无控制台时Uvicorn日志初始化问题。关闭测试浏览器后服务仍响应。登录自启真实状态保持关闭，开关注册表行为通过mock测试，未修改用户真实启动项。 |
| 隔离 | Windows DPAPI加密回读测试通过；凭据API只写不回显。Codex专用配置关闭插件/工具/记忆/钩子，仅给快照目录及最小系统读取权限。输入白名单和子进程环境测试证明不含账户ID、股数、金额、成本、流水、券商或QQ凭据。Git忽略规则验证通过，无远程仓库。 |

测试框架出现一条Starlette关于httpx兼容层的弃用提示，不影响上述通过结果；运行看板的新浏览器会话没有该提示。

## 回放

实际运行：

```powershell
.venv\Scripts\python.exe -m signaldesk.replay --output .runtime\replay-demo.json
```

本次15分钟合成序列为3023根K线，常规时段546个有效评分快照、51个历史融合事件。时间推进后生成器长度和事件数量会变化；指定同一时间/输入时结果可复现。报告只包含技术事件，不能解释为回测收益。

回放、实时共用 `enrich → summarize → EventEngine`，CSV/JSON入口共享字段默认值并强制要求带时区时间。缺口/过期/无效窗口不生成新评分，历史事件不进入实盘新机会通知。趋势、反向趋势与量能变化由演示生成器提供；流动性不足与数据丢失边界由自动测试约束。

## 本机验收产物

截图在 `output/playwright/`，回放报告在 `.runtime/replay-demo.json`，均被Git忽略：

- `dashboard-release.png`：最终深色看板，包含真实Codex对合成快照的结构化判断。
- `dashboard-light-1280.png`：浅色笔记本窗口。
- `qq-settings.yml`、`allocation.yml`、`preview.yml`：接入、分仓与发送预览的浏览器快照。

## 尚需本机真实配置的部分

1. LongPort需填写自己的OpenAPI凭据并获得对应时段行情权限，再切换实盘、核对实际持仓分类。已核对安装版SDK签名及公开日线时间戳口径；**未读取用户真实账户，未完成实盘长时间联调**。
2. QQ需配置本AppID对应的user_openid/group_openid及平台主动消息/订阅权限，再在设置中点击测试，以平台回执和接收端为准。消息、频率和授权受官方平台约束，首版没有公网回调/OpenID自动采集服务。接口与错误码依据[官方访问凭证文档](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/access-token.html)及[调用指南](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/api-call-guide.html)核对。
3. Linux无界面路径已保留，尚未在Linux/ARM64目标机器实测。尚未完成连续24小时实盘和断网恢复压力验收。

这些限制在界面和使用说明中保留明确状态。无行情、QQ受限或Codex失败不会变成“没有风险”的结论。
