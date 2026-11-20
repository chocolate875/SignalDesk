# V0.1.0 验收记录

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
