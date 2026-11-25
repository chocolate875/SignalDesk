# V0.1.0 验收记录

## 2026-11-26 长桥调用调度与看板布局

- 使用模拟长桥接口验证 137 个跨市场标的合并为一次报价请求，已订阅标的保留订阅。推送正常时无需定时重拉，报价缺失、停更、队列溢出时按标的补查。
- 测试覆盖日线缓存命中、休眠后的缺口补齐、同步期间继续消费行情，以及触及历史频率与月度额度后的退避。真实长桥账号的调用量留待实盘观察。
- Playwright 在 1440×810 与 1280×720 下验证自选同步占一行，高 23px，最小字号 12px。风控警示和采纳计划价并排，可用键盘展开警示或打开已预填计划价的弹窗。
- 全量 pytest 140 项、Ruff、前端生产构建与私有运行文件审计通过。CSS 字号审计共 301 处，均达到 12px。

## 本地数据清理脚本

- 在独立演示目录启动 Windows 无托盘服务，再用 `Clean-SignalDesk.cmd cache` 确认清理。服务正常退出，SQLite 的 K 线记录从 10,985 条降到 0。
- 测试覆盖缓存模式保留设置与凭据、重置模式删除指定数据库及应用生成文件、保留同目录其他文件，以及取消清理时保留运行中的实例。

## 2026-11-26 证券资料与局域网访问

- Chromium 使用隔离演示库，从私有 IPv4 登录。尝试错误访问码后用正确访问码进入，收到 WebSocket 快照，设置接口返回 403，快照省略账户数量。1440×810 与 1280×720 下验证五位港股编号、中文名称、分类标记、市场切换及 K 线。
- 全量 pytest 133 项通过。前端生产构建、Ruff 和私有运行文件审计通过。
- 本机数据库迁移后港股和沪深 K 线行数为 0，美股缓存保留。新版服务在原端口恢复实盘同步，内网未登录的看板请求返回 401。
- 迁移测试覆盖旧港股代码、分组与估值键、只清理指定市场的 K 线及重复启动保留新缓存。分类测试区分上证指数和平安银行，覆盖港股指数、港股和沪深 ETF、杠杆及反向产品、权证。

## 2026-11-25 多市场选股栏本地验收

- 使用独立演示库验证 8 只美股、1 只港股和 2 只沪深 A 股。Chromium 在 1440×810、1280×720 下切换市场、选择标的并核对对应 K 线与计价币种。市场按钮和价格行均通过边界检查，页面无横向溢出。
- 自选分组和市场条件取交集。港股支持补零搜索 `00700`，深市搜索 `000001` 保留前导零。API 测试覆盖手动添加、收藏与移除港股，以及模拟券商混合市场持仓、自选合并和分市场估值权限错误。
- 日期用例覆盖香港和沪深当地午夜日线、午休、节假日、半日市及港股收市竞价。仓位用例覆盖同币种净资产、缺少换算分母和人民币港股柜台的报价币种。
- 前端生产构建与 Ruff 通过。CSS 字号审计共 301 处，最小值 12px。券商接口使用测试替身验证，真实长桥账号的数据权限和行情需要在验收账户中核对。

## 2026-11-25 GitHub 多人协作基线

- **发布内容**。在临时目录用 `git clone --no-local` 复现 Git 传输。克隆内的分支与标签历史中无 `.agents/skills/` 路径，逐一查询原目录的 19 个文件对象均返回 `missing`。本机原始提交历史已归档至 `refs/archive/before-skill-cleanup`。
- **中文提交**。在临时克隆启用钩子后，实际提交 `fix(chart): 修复缩放范围丢失` 成功，纯英文摘要被拒绝。PR 校验接受规范的中文标题，拒绝英文摘要和缺少类型的标题。历史检查能够发现先添加、后移除的技能文件，普通合并可通过。
- **全新安装**。Windows 临时克隆执行 `uv sync --frozen`、Ruff、`pytest -q`、`npm ci` 与前端生产构建成功。111 项测试通过，依赖产生 1 条 Starlette TestClient 弃用提示。项目 CSS 共 299 处显式像素字号，最小值为 12px。
- **远程启用**。GitHub Actions 工作流已通过本地 YAML 解析。GitHub 托管运行和保护规则在首次推送后按 [协作指南](../CONTRIBUTING.md) 验收。

## 2026-11-25 交接清单 5 项界面精修、COMEX 黄金双源、因果筹码分布与中级波浪升级

- **5 项交接清单落地与顶栏/K 线交互精修。**
  - **K 线默认视图与跨股缩放保持（[Chart.tsx](../frontend/src/Chart.tsx)）**：将默认范围由 `252` 根改为「近6月」（`DEFAULT_RANGE_BARS = 126`），默认关闭 `MACD` 副图（`showMacd = false`，并在 [GuidePopover.tsx](../frontend/src/GuidePopover.tsx) 标明 `动能强弱 · 默认关闭`）；移除与「近3月（63根）」重复的「最新（60根）」按钮（精简为 `近3月 / 近6月 / 近1年 / 全部`）；建立跨标的共享的视图窗口与二分日期映射（`sharedViewWindow` + `resolveViewWindow`），切换不同标的时严格保持当前缩放跨度与历史时间位置一致。
  - **顶栏去重与外置三态主题（[App.tsx](../frontend/src/App.tsx)、[style.css](../frontend/src/style.css)）**：精简 `TopbarMoreMenu` 移除重复的连接状态、外观主题与市场大势入口（仅留京/纽双时钟、涨跌配色、通知投递记录）；新增 `ThemeModeSwitch`（`role="radiogroup"` 支持方向键导航，`height: 32px`）外置顶栏右侧，支持 `light / dark / system` 三态并实时监听 `prefers-color-scheme`，同步更新 `document.documentElement`、`meta[name="theme-color"]` 与 ECharts 配色。
  - **COMEX 黄金公开双源接入（[research.py](../signaldesk/research.py)、[demo.py](../signaldesk/demo.py)、[service.py](../signaldesk/service.py)、[security.py](../signaldesk/security.py)、[GuidePopover.tsx](../frontend/src/GuidePopover.tsx)）**：实现 `parse_yahoo_comex_gold()` / `parse_eastmoney_comex_gold()` / `fetch_comex_gold()`（Yahoo `query1`/`query2` `GC=F` → 东方财富 `101.GC00Y` 热备，避免将 2 个月前 `chartPreviousClose` 误作昨收）与 `gold_context()`（联动 10Y TIPS 实际利率解读）；`Monitor.refresh_macro()` 每 5 分钟刷新并缓存 `comex_gold:live`；`snapshot()` 顶层输出 `gold` 并纳入 `safe_snapshot()` 白名单透传；顶栏胶囊并列展示 `美债10Y · COMEX金`（`<=1360px` 隐藏涨跌幅后缀），二级弹层新增通栏「COMEX 黄金主力与 10Y TIPS 实际利率联动」卡片。
- **因果筹码分布（Volume Profile）、核心突破/防守位与中级波浪升级。**
  - **因果筹码引擎与点位呈现（[forecast.py](../signaldesk/forecast.py)、[Chart.tsx](../frontend/src/Chart.tsx)、[StockInspector.tsx](../frontend/src/StockInspector.tsx)）**：新增 `compute_volume_profile()`（126 日三角典型价核 + 90 日半衰期，提取 `POC`、`VAL–VAH`、上下筹码峰 `HVN`、低量真空 `LVN` 与获利/套牢占比），将其与波浪前高/前低和 60 日移动保护共振提炼 `breakout_level`（主要突破位）与 `defense_level`（主要防守位）；K 线主图升级为动态可见窗口紧密 Y 轴（`computeTightPriceBounds` + `datazoom` 实时贴合，显著消除大片上下留白）、买卖区半透明色带（`markArea`）、防重叠碰撞调度的 `▲ 突破 / ▼ 防守` 主线与右侧可一键开关的半透明水平筹码直方图（`custom` series）。
  - **中级波浪回溯时长升级（[wave_trend.py](../signaldesk/wave_trend.py)、[WaveTrendSection.tsx](../frontend/src/WaveTrendSection.tsx)）**：依据 Frost & Prechter、Lunde & Timmermann (2004) 与 Pagan & Sossounov (2003) 文献，将趋势通道窗口由 `90` 日升至 `126` 日、因果拐点滤网由 `max(2.2×ATR14, 4.5%)` 升至 `max(2.8×ATR14, 6.5%)`、可见拐点上限扩至 `16` 个并输出波浪跨度 `span_days` 与 `degree_label`；顺手修复 [test_desktop_and_gaps.py](../tests/test_desktop_and_gaps.py) 在开盘首小时因依赖墙上时钟偶发的 flaky 边界。
- **自动化验证与双分辨率浏览器复核。**
  - 新增 COMEX 黄金双源解析/降级/联动、筹码分布双峰识别/零量降级及中级波浪 126 日通道单元测试；`ruff check signaldesk tests` 零告警，全量 `pytest -q` **111 项全部通过**，全站 CSS `299` 处 `font-size` 最小值保持 `12.0px`（`bad = 0`），`tsc -b && vite build` 零错误构建通过；
  - 在 `1440×810` 与 `1280×720` 双视口下完成隔离演示实例端到端浏览器复核与两轮细节打磨：顶栏 `52px` 单行零溢出、三态主题与「更多」精简菜单正常、`美债10Y · COMEX金` 弹层完整、`1280×720` 自动隐藏黄金涨跌后缀、主图 Y 轴紧密贴合 K 线、突破/防守/POC/持仓成本/计划失效标签自动错位零重叠、波浪低点胶囊不被底边裁切，全程控制台 **0 errors**。

## 2026-11-24 项目区前端设计技能（`.agents/skills/`）安装与安全审查

- 当日在开发机安装了 `frontend-design`、`web-design-guidelines`、`vercel-composition-patterns` 和 `emil-design-eng`。技能文件仅保存在开发者本机。
- **安全审查与仓库验证**：逐一审查各 `SKILL.md` 及关联文件（无敏感路径读取、无外传命令、无提示词注入）；运行 `ruff check signaldesk tests` 零警告、`pytest tests/test_integrations.py -k test_no_private_runtime_files_tracked -q` 通过、全量 `pytest -q` **108 项全部通过**。

## 2026-11-24 多 Agent 长期复核泛化、Google Antigravity CLI 官方 ACP 接入与 Codex 官方接口核查

- **官方协议合规核查（严格拒绝一切非官方调用方式）。**
  - **OpenAI Codex CLI 核查结论**：确认现有 [codex_bridge.py](../signaldesk/codex_bridge.py) 使用的是 OpenAI 官方公开支持的非交互命令 `codex exec`（配合 `--ignore-user-config --ephemeral --skip-git-repo-check --output-schema -o` 及最小目录只读权限 `-c permissions=...`），不含任何屏幕抓取、伪终端注入或私有 API；鉴于 OpenAI 官方原生不含 `codex acp`（社区 `codex-acp` 为第三方适配器），Codex 严格保持官方原生 `codex exec` 通道。
  - **Google Antigravity CLI 官方 ACP 接入**：依据官方文档 [Agent 客户端协议 (ACP)](https://antigravity.google/docs/cli/acp/) 新建 [agent_bridge.py](../signaldesk/agent_bridge.py)，实现标准 `AcpStdioClient`、`AntigravityAcpBridge` 与多引擎协调器 `AgentHub`：
    - 通过官方 `agy acp` 子命令执行标准 JSON-RPC 2.0 over stdio 生命周期（`initialize` → `session/new` → `session/prompt`）并聚合 `session/update`（`agent_message_chunk`）；
    - 协议层硬隔离：`initialize` 显式声明 `clientCapabilities = {fs: {readTextFile: false, writeTextFile: false}, terminal: false}`，`session/new` 设 `mcpServers = []`，遇到任何 `session/request_permission` 工具授权请求一律自动回复 `reject_once` / `cancelled`，遇到反向能力调用一律返回 `-32601` 拒绝；
    - [security.py](../signaldesk/security.py) 子进程环境白名单扩展 `GEMINI_API_KEY` / `GOOGLE_API_KEY` / Vertex AI 官方认证变量，继续严格屏蔽 `LONGPORT_*`、`QQ_*` 与 `SIGNALDESK_VAULT_KEY`；
    - [models.py](../signaldesk/models.py) 与 [app.py](../signaldesk/app.py) 限定 `AgentProviderId = Literal["codex", "antigravity"]`，任何非官方 Agent 参数一律返回 HTTP `422` 拒绝。
- **前端多 Agent 泛化与配置面板升级。**
  - 更新 [types.ts](../frontend/src/types.ts)、[App.tsx](../frontend/src/App.tsx)、[StockInspector.tsx](../frontend/src/StockInspector.tsx)、[Settings.tsx](../frontend/src/Settings.tsx) 与 [style.css](../frontend/src/style.css)：将入口与面板升级为「`AI 复核` / `智能体长期复核`」，支持 `Antigravity CLI (官方 ACP · agy acp)` 与 `Codex CLI (官方 · codex exec)` 双引擎切换、跨引擎已有复核结论对照、脱敏发送预览动态标注及「设置 → Agent 复核」默认首选引擎与独立超时配置；全量 `288` 条 CSS `font-size` 最小值为 `12.0px`（`bad = 0`）。
- **自动化测试与双分辨率实盘验收（`http://127.0.0.1:8765/`）。**
  - 新增 [test_agent_bridge.py](../tests/test_agent_bridge.py)（真实子进程 stdio ACP 握手、流式分片、思考分片隔离、`session/request_permission` 自动拒绝、超时强杀、未登录路径脱敏与非官方 Agent `422` 拦截）；全量 `ruff check signaldesk tests` 零警告，`pytest -q` **108 项全部通过**，前端 `tsc -b && vite build` 零错误通过（产物 `index-Dn5f2ae8.js`、`index-DzCbu28j.css`）。
  - 完成 `1440×810` 与 `1280×720` 双分辨率浏览器验收：`AI 复核` 双引擎卡片切换、协议说明、`agy acp --login` 引导、「Agent 脱敏发送预览」（确认含学术因子与风险预算、零股数/成本泄露）、「设置 → Agent 复核」与「提醒动态 → 接入与通道状态」全部渲染正常，全程控制台 **0 errors**，`.error-fallback = 0`。

## 2026-11-24 Phase 0–4 学术因子升级、`fusion-2.0.0` 规则降噪浓缩与 16:9 界面全链路验收

- **Phase 0 本机因果回放实证基准（`75` 只非杠杆美股 / `9,307` 观测 / `138` 截面）。**
  - 新建严格因果评测脚本 [factor_eval.py](../signaldesk/factor_eval.py)（只读读取 `live-fwd-v3` 与 `macro-live-fwd-v3` `SPY` 基准，严禁读取账户与持仓表），实证结果归档于 [research.md](./research.md)：
    - 原短窗口指标高度共线：`zscore20 <-> rank20` Spearman 达 `0.947`，`rsi14 <-> zscore20` 达 `0.866`，`macd_hist_atr <-> zscore20` 达 `0.724`；
    - 原 30% 权重单日量价分 `volume_v1_1d` 未来 5/20/60d RankIC 全负（`-0.0087 / -0.0103 / -0.0029`），升级为 10 日平滑资金顺向度 `volume_v2_flow10` 后 20/60d RankIC 转正至 `+0.0309 (ICIR +0.173) / +0.0294`；
    - 新学术因子 `residual_mom_z`（扣 `SPY` Beta 不扣自身 Alpha，剔除近 21 日）5/20/60d RankIC 全正（`+0.0272 / +0.0458 / +0.0309`），`neg_info_discreteness` 5/20d 为正（`+0.0209 / +0.0131`），`overnight_20d_pct` 20d 达 `+0.0423`；
    - 近 60 日峰值 `2.5×ATR14` 移动保护（`4,656` 样本）将 20d 平均最大回撤由 `-10.59%` 压至 `-8.63%`、60d 平均最大回撤由 `-19.03%` 压至 `-10.21%`（仅作盈利保护参考，不替代固定长期失效价）。
- **Phase 1–3 后端引擎升级与风险预算闭环。**
  - 新建 [factors.py](../signaldesk/factors.py) 实现 `compute_academic_factors()` 与 `compute_yang_zhang_hv()`；升级 [indicators.py](../signaldesk/indicators.py) 至 `RULE_VERSION = "fusion-2.0.0"`（默认权重平滑迁移为 `趋势 45% / 动量 40% / 量价 15%`，移除 `zscore20 / rank20 / corr20`）；[providers.py](../signaldesk/providers.py) 零额外请求追加 `TurnoverRate` 与 `TotalMarketValue`；[instruments.py](../signaldesk/instruments.py) 优先采用 Yang-Zhang 波动率；[extended_hours.py](../signaldesk/extended_hours.py) 新增 `tug_of_war` 日夜拉锯拆解与高开低走防追高预警；[forecast.py](../signaldesk/forecast.py) 去重 20 日均线/布林中轨锚点、消除 `RSI/MA20 偏离` 二次扣分、新增 `MAX5` 彩票过热护栏及顶层 `risk_budget`（含 `suggested_exposure_ratio` 与 `trailing_stop`）；[security.py](../signaldesk/security.py) 白名单扩展脱敏学术字段且零持仓隐私泄露；[service.py](../signaldesk/service.py) 消除 `verdict.headline` 多分数冲突并支持 `live-eval` 全链路试算联动。
- **Phase 4 前端浓缩升级、自动化测试与双分辨率实盘验收（`http://127.0.0.1:8765/`）。**
  - 更新 [types.ts](../frontend/src/types.ts)、[App.tsx](../frontend/src/App.tsx)、[StockInspector.tsx](../frontend/src/StockInspector.tsx)、[WaveTrendSection.tsx](../frontend/src/WaveTrendSection.tsx)、[Settings.tsx](../frontend/src/Settings.tsx)、[GuidePopover.tsx](../frontend/src/GuidePopover.tsx)、[inspectorModules.ts](../frontend/src/inspectorModules.ts) 与 [style.css](../frontend/src/style.css)（全量 `281` 条 `font-size` 最小值 `12.0px`，`bad = 0`）。
  - 新增 [test_academic_factors.py](../tests/test_academic_factors.py)（5 项因果/慢牛vs脉冲/日夜拉锯/Yang-Zhang+宏观风险预算/脱敏隔离测试）；后端 `ruff check signaldesk tests` 全通过，`pytest -q` **104 项全部通过**，前端 `tsc -b && vite build` 零错误通过（产物 `index-DWwJOYUJ.js`、`index-D3dNbbfp.css`）。
  - **`1440×810` 与 `1280×720` 双分辨率浏览器终验**：
    - `NVDA` 评级卡渲染 `敞口 0.20x` 胶囊，底部操作行弹性折行无竖压、零右侧裁切；波浪计数默认折叠在二级 `<details>` 内；盘外动态呈现 `近20日 隔夜 +15.0% · 盘中 -33.5% 高开低走特征`；长期计划价位呈现 `60日峰值 $243.37 · 移动保护 $210.31` 且一键「采纳保护」准确预填弹窗；「结构评分与学术因子」2 列×3 行网格完整展示 6 项核心学术因子无省略截断，展开抽屉显示 `近60日偏度 / 相对SPY Beta / Amihud冲击`；估值注脚展示 `总市值 $3.98T · 换手率 3.35%`；切换「最新试算 ↔ 收盘确认」全模块实时联动，全程控制台 **0 errors**，`.error-fallback = 0`。

## 2026-11-24 网页品牌图标补齐与右侧研判栏模块化自定义排序重构

- **网页图标（Favicon）补齐与静态路由修复。**
  - 新增与 SignalDesk 品牌视觉一致的多格式图标：[favicon.svg](../frontend/public/favicon.svg)（矢量深蓝渐变圆角 + 上升信号脉搏线 + 翠绿信号点）、[favicon.ico](../frontend/public/favicon.ico)（16/32/48px 多尺寸超采样抗锯齿）与 [apple-touch-icon.png](../frontend/public/apple-touch-icon.png)（180×180px）。
  - 在 [index.html](../frontend/index.html) 补全 `icon (svg/ico)`、`apple-touch-icon` 与 `theme-color` 声明；在 [app.py](../signaldesk/app.py) 的 SPA 兜底路由前增加图标静态白名单，避免浏览器请求 `/favicon.*` 被兜底返回 `text/html`。
- **右侧研判栏全面模块化与自定义显隐/排序。**
  - 新建 [inspectorModules.ts](../frontend/src/inspectorModules.ts) 建立 7 大研判模块注册表（`forecast`、`wave_trend`、`extended_hours`、`plan_range`、`daily_score`、`valuation_profile`、`risk_check`）、本地持久化 Hook（`localStorage` 键 `signaldesk:inspector-layout:v1`，带非法数据自动清洗与新模块补齐）及显隐/上下移/拖拽重排/恢复默认纯函数。
  - 重构 [StockInspector.tsx](../frontend/src/StockInspector.tsx)：将原内联大区块全部抽离为独立模块组件（`DailyScoreCard`、`ValuationOrFundCard`、`RiskCheckCard` 等），默认按 **`买卖点位评级 → 波浪与趋势分析 → 盘外动态 → 长期计划价位 → 日线结构评分 → 估值与资产特征 → 独立风险检查`** 置顶排布；顶部改为 `32px` 单行控制栏（左侧紧凑双口径切换 `收盘确认 | 最新试算`，右侧 `模块` 自定义入口），点击展开 `InspectorModuleManager` 支持**拖拽排序、上/下移箭头微调、拨动开关显隐、隐藏数角标提示与一键恢复默认**。
  - 更新 [style.css](../frontend/src/style.css) 新增控制栏、开关、拖拽落点高亮及空态引导样式，全量 `275` 条 CSS `font-size` 最小值保持 `12.0px`（`bad = 0`）。
- **自动化测试与实盘浏览器端到端验收（`http://127.0.0.1:8765/`）。**
  - 在 [test_api.py](../tests/test_api.py) 新增 `test_favicon_routes_return_icon_media_types`；后端全量 `pytest -q` **99 项全部通过**，`ruff check signaldesk tests` 全通过，前端 `tsc -b && vite build` 零错误通过（产物 `index-CSO5TDmU.js`、`index-oo_w2t_2.css`）。
  - 重启本地实盘服务并完成双分辨率浏览器端到端验收：
    - **图标响应**：`/favicon.svg`（`image/svg+xml`, `1511B`）、`/favicon.ico`（`image/x-icon`, `6616B`）、`/apple-touch-icon.png`（`image/png`, `19405B`）均返回 HTTP `200`；
    - **`1440×810` 默认首屏**：`.inspector-ctrl-bar` 仅 `32px` 高，首屏无需滚动即完整呈现「买卖评级与点位预测」（`forecast`, `y=162`）与「波浪与趋势结构」（`wave_trend`, `y=493.8`，直览趋势结论与 3 条波浪拐点明细）；
    - **自定义显隐、调序与刷新持久化**：隐藏 `extended_hours` 与 `plan_range` 并上移 `wave_trend` 后，顶部实时亮出 `模块 5/7`、列表顺序即刻变为 `wave_trend → forecast → daily_score → valuation_profile → risk_check`；刷新页面后配置 100% 持久保持；点击「恢复默认」精确还原 7 模块默认排序；
    - **`1280×720` 与双口径回归**：整页无水平溢出，`.inspector-ctrl-bar` 单行无折行，切换「最新试算 ↔ 收盘确认」实时联动无异常，全程控制台 **0 errors**，`.error-fallback = 0`。

## 2026-11-24 16:9 界面视野减负、顶栏精简与二级菜单收纳重构

- **16:9 拥挤痛点诊断（覆盖 `1440×810` 与 `1280×720`）。**
  - 原顶栏高度 `64px` 挤满 11 个平铺元素（含 ~380px 四段美债长条、独立时钟/连线/配色/主题/通知胶囊），中栏 Hero 与多层结论卡纵向占用过高导致 K 线主图区在 `1440×810` 下仅约 `430px`；右栏首屏平铺大量护栏警示全文、点位依据、评分细则、维度长注脚与底部免责声明，干扰核心决策信息阅读。
- **核心改动（纯前端视觉与信息层级重构，零后端侵入）。**
  - **顶栏极简化与「更多」二级菜单**：[App.tsx](../frontend/src/App.tsx) 新增 `TopbarMoreMenu` 二级下拉面板，集中收纳实时连线状态、京/纽双时钟、涨跌配色切换、明暗主题切换、通知投递记录与市场大势全景入口；将左区模式/时段/连线合并为单个 `.status-pill-merged`（如 `实盘 · 夜盘`），顶栏由 11 项精简至 6 项，高度由 `64px` 压至 `52px`。
  - **美债看板紧凑化**：[GuidePopover.tsx](../frontend/src/GuidePopover.tsx) 将顶栏美债长条精简为单个胶囊 `美债10Y 4.92%`（异常/过期时显示微圆点提示），点击展开原完整 6 项美债二级解读弹层与宏观大势直达入口。
  - **中栏 Hero 与紧凑结论卡**：[App.tsx](../frontend/src/App.tsx) 精简按钮为 `计划` / `Codex` 并避免持仓/ETF 徽章挤压截断；将 `.verdict-banner` 压缩为双行精简卡（第 1 行徽章 + 单行结论 + `详情 ▾`；第 2 行买点/卖点/止损/赔率快捷条），下一步行动建议与三支柱拆解收纳进默认折叠的 `.verdict-drawer`（切股自动收起）。
  - **右侧详细说明、风控警示与免责声明全部入二级区**：[StockInspector.tsx](../frontend/src/StockInspector.tsx) 重构 `ForecastCard`，一级仅展示评级、3 格点位、位置/置信度、琥珀色 `风控警示 N` 胶囊按钮与 `采纳计划价`，将全部护栏警示全文、买卖/止损依据、四维评分拆解与免责声明统一收进 `<details className="insp-sub-details">`；压缩「最新行情试算」提示横幅为单行；将「日线结构评分」的 3 条维度长注脚与 6 项原始技术指标合并折叠；[WaveTrendSection.tsx](../frontend/src/WaveTrendSection.tsx) 将底部两行免责声明移入二级弹窗 `modal-footer`，标题旁按钮精简为 `说明`。
  - **16:9 三栏比例与 `1280×720` 紧凑断点**：[style.css](../frontend/src/style.css) 优化三栏宽度为 `268px / 1fr / 340px`（`<=1360px` 降至 `248px / 1fr / 312px`，`>=1680px` 扩至 `304px / 1fr / 380px`），并在文件尾部新增 `@media (max-width: 1360px)` 紧凑规则（收紧 `.chart-toolbar` / `.toolbar-group button` / `.toolbar-help-btn` / `.toolbar-fs-btn` / `.rail-subbar` 间距与单行锁定）及 `.wt-head-left h3` 单行防折行。
- **构建审计与双分辨率实盘浏览器验收（`http://127.0.0.1:8765/`）。**
  - CSS 最小字号全量审计：`263` 处 `font-size` 声明最小值为 `12.0px`（`bad = 0`）；`tsc -b && vite build` 生产构建零错误通过（产物 `index-DJ949_F_.js`、`index-DNgDQQVT.css`）。
  - **`1440×810` 实盘验收**：`.desk-topbar` 稳定 `52px`；`.chart-panel-card` 高度由改造前 `~430px` 提升至 **`549.8px`**（`.price-chart` 画布达 **`790 × 473.4px`**），图顶 HUD `MA20 / MA50 / MA200` 完整无截断；右侧首屏直览「双口径切换」「盘外动态」「买卖评级与点位预测」「波浪与趋势结构」；「波浪与趋势结构」标题（`25.6px` 高）与「说明」按钮单行工整；顶栏「更多」下拉、美债六项弹层、中栏「详情」抽屉、右侧点位/评分/风控折叠区交互全部流畅正常。
  - **`1280×720` 紧凑 16:9 实盘验收**：整页宽度严格 `1280px` 无水平溢出；`.chart-panel-card` 高度 `463.8px`（`.price-chart` `686 × 391.4px`）；`.chart-toolbar` 最右「全屏」按钮完全可见且距右缘留白 `+8px`；左栏 `.rail-subbar` 的「共 93 只」单行高度 `19.2px` 不折行；右栏「波浪与趋势结构」标题单行 `25.6px`；全程控制台 **0 errors**，`.error-fallback = 0`。

## 2026-11-24 SOXL 等 10 股波浪断档修复、全量前复权升级与「最新行情试算」双口径引擎

- **根因排查（全库 94 只实盘日线诊断）。**
  - **波浪待确认（10 股 `swings = 0`）**：[forecast.py](../signaldesk/forecast.py) 中 `_contiguous_regular_tail()` 仅用 `breaks == breaks.iloc[-1]` 切片而未叠加 `valid` 掩码，导致历史中存在 1 根无效 `NaN` 断档行（例如 `2023-06-05`）时把该 `NaN` 行本身误包含在了连续尾部第 0 行；`_causal_swings()` 初始化 `hi_val = highs[0] = NaN`，造成后续全部 870 根比较恒为 `False`，使 `SOXL`、`BRK.B`、`APH`、`COPX`、`GLW`、`SOXS`、`SPOT`、`TTE`、`USO`、`WOLF` 共 10 只标的拐点归零、波浪长期显示「待确认」。
  - **拆股与合股断崖（22 股受不复权扭曲）**：此前拉取 `AdjustType.NoAdjust`（不复权）导致 `SOXX`（`2026-11-05` 3:1 `-70.7%` 与 `2024-03-07` 3:1 `-65.5%`）、`NVDA`（10:1）、`SNDK`（`2026-11-20` 10:1）、`AVGO`、`NFLX`、`MSTR`、`APH`、`TQQQ`、`QLD`、`SQQQ`、`SOXS`、`YANG` 等 22 只标的均线、ATR、回撤与波浪受虚假除权悬崖严重扭曲。
- **核心改动。**
  - **波浪断档根治**：[forecast.py](../signaldesk/forecast.py) 修复 `_contiguous_regular_tail()` 为 `reg[valid & (breaks == breaks.iloc[-1])]` 并严格校验 OHLC 有限正数；[wave_trend.py](../signaldesk/wave_trend.py) 在 `_causal_swings()` 增加前置有限数防御过滤。
  - **全量前复权与除权自动自愈**：[providers.py](../signaldesk/providers.py) 将历史 K 线升级为 `lp.AdjustType.ForwardAdjust`（前复权，最新价与真实市场价一致且平滑消除拆股/合股跳空）；[storage.py](../signaldesk/storage.py) 升级缓存分桶至 `live-fwd-v3` / `macro-live-fwd-v3` 并新增原子重写方法 `replace_bars()`；[service.py](../signaldesk/service.py) 新增 `_detect_split_adjustment()`，增量拉取若检测到重叠交易日收盘价变动 `> 0.5%` 自动触发全量前复权重写并重建指标。
  - **「最新行情试算」双口径引擎**：[service.py](../signaldesk/service.py) 新增 `live_evaluation_for()` 与 [app.py](../signaldesk/app.py) 新增只读端点 `GET /api/stock/{symbol}/live-eval`（仅对当前选中个股按需计算，优先使用盘中实时 OHLCV、非盘中回退盘前/盘后/夜盘有效价格并标注流动性），100% 复用同一套 `enrich → summarize → compute_wave_trend → compute_fund_metrics → compute_forecast` 引擎产出临时试算结果，绝不写入数据库或触发正式告警；[types.ts](../frontend/src/types.ts)、[App.tsx](../frontend/src/App.tsx)、[StockInspector.tsx](../frontend/src/StockInspector.tsx)、[Chart.tsx](../frontend/src/Chart.tsx)、[style.css](../frontend/src/style.css) 新增右侧顶部「收盘确认 / 最新行情试算」双口径分段切换、实时对比横幅、4 秒节流重算及整页（结论卡 / K 线参考线与当日均线 / 波浪 / 买卖评级）一键联动预览，并将全屏标题更新为「常规时段 · 前复权」。
- **自动化测试、构建与 1440×810 实盘复验。**
  - 新增 `tests/test_splits_and_live_eval.py`（4 项测试，覆盖 `NaN` 断档后波浪恢复、3 拆 1 因子漂移检测与 `replace_bars`、盘中实时试算零污染、盘前低流动性回退试算）；全量 `pytest -q` **98 项全部通过**，`ruff check signaldesk tests` 通过，CSS 全部 `250` 条 `font-size` 最小值为 `12.0px`，前端 `tsc -b && vite build` 生产构建通过（产物 `index-DqIVxcQ_.js`）。
  - 重启本地实盘服务并完成 `1440×810` 浏览器全量复验（`http://127.0.0.1:8765/`）：
    - `93` 只自选「待更新」为 `0`，控制台 **0 errors**，`.error-fallback = 0`；
    - **`SOXL`**：波浪恢复为 `下降趋势 · 下降五浪推动 · 下跌第5浪`（置信度高，清晰标出 `起 $169.83 → 1浪 $80.22 → 2浪 $108.60 → 3浪 $40.59 → 4浪 $69.73 → 5浪* $29.82`，反转位 `$69.73`）；
    - **`SOXX`**：`2026-11-05` 与 `2024-03-07` 两次 3 拆 1 断崖彻底消除，近 1 年（`60–240`）与全部（`0–250`）走势连续平滑，准确识别 `下降趋势 · 下跌第3浪`（`起 $174.63 → 1浪 $130.75 → 2浪 $158.58 → 3浪* $122.20`）；
    - **`NVDA`**：4 年「全部」视图 10 拆 1 断崖彻底消除（Y 轴 `0–300`）；一键切换「最新行情试算」后，蓝底横幅呈现 `盘中实时试算 · $165.42 (+31.78%) · 日线分 +35.5 · 谨慎减持 → 中性观望`，中栏亮出 `实时试算 · 未收盘` 胶囊，日线评分由 `6.5` 联动试算至 `42.1`、评级升至 `中性观望 51.3分`、波浪实时演进为 `潜在下跌第2浪反抽（2浪* $171.50）`；点击「重算」`GET /api/stock/NVDA.US/live-eval` 返回 HTTP `200`；切回「收盘确认」所有基准数值精确还原零污染。

## 2026-11-24 最新盘中 K 线选中交互稳定性与图面边缘渲染修复

- **问题复现与根因定位。**
  - 在实盘盘中（`http://127.0.0.1:8765/`，`1440×810`）对 `NVDA`（「近1年」「最新」「全部」）、`ADT`、`SQQQ`、`ANT` 的最右侧当日实时 K 线（`2026-11-23`）执行逐像素悬停、点击及多轮 WebSocket 实时推送复测，定位出 6 项直接导致「选上去出问题、最右侧渲染异常」的根因：
    1. WebSocket 每秒推来新报价时 `Chart.tsx` 对整图执行 `setOption(..., { notMerge: true })`，强行销毁重建坐标系、Tooltip 与十字准星，导致悬停最新 K 线 1 秒内浮窗即消失；
    2. ECharts 默认 `tooltip.triggerOn: "mousemove|click"` 且有过渡动画延迟，点击最新 K 线柱体上下空白区时直接触发 `hideTip` 关闭弹窗；
    3. `candlestick` 数据中对 `intraday_forming` 混入 `{ value, itemStyle: { opacity: 0.78, borderType: "dashed" } }` 与纯数组，且默认启用 `large: true`（阈值 `600`），导致实体与上下影线被切碎发虚，且在「全部」1001 根视图下与普通系列索引错位；
    4. 所有子图 `xAxis.axisPointer` 默认同时渲染日期浮标，悬停最右侧 K 线时 3 个子图在右下角垂直叠加 3 个蓝色 `2026-11-23` 标签盖死 Y 轴数字；
    5. 多子图垂直间距过窄（~7px）且主图价格轴未限制非负下限，造成主图底刻度与成交量 `900.0M` 撞车重叠，以及「全部」视图下出现 `-300.00` 负股价刻度；
    6. 右侧靠边波浪拐点胶囊向右溢出遮挡最新 K 线与 Y 轴，且窄屏下 `.ohlc-hud` 折行易引发画布高度抖动。
- **修复内容。**
  - [Chart.tsx](../frontend/src/Chart.tsx)：① 拆分「结构性重建（`notMerge: true`）」与「盘中实时价格/成交量增量刷新（`notMerge: false` 仅更新 `price`/`volume` 两个 series 的 `data`）」；② 统一全部 K 线为纯数组 `[open, close, low, high]` 并关闭 `large`、`selectedMode`、限制 `barMaxWidth: 28`，成交量实时柱去除虚线毛边；③ `tooltip` 设为 `triggerOn: "mousemove"`、`transitionDuration: 0`，`formatter` 通过 ref 读取最新行情并加全量边界校验与 `try/catch` 兜底；④ 仅最底部子图显示 `xAxis.axisPointer.label`，重排 2/3/4 窗格垂直槽位间距（每层留白 25px+），主图价格 Y 轴钳制下限 `>= 0`、`grid.right = 80`、`yAxis.axisLabel.margin = 12`；⑤ 右边缘波浪拐点标签改为 `align: "right"` 向左展开，`dataZoom` 统一传安全整数索引；⑥ 精简 HUD 盘中提示为 `未收盘 · 指标按已收盘计` 并复用单例 `Intl.DateTimeFormat`。
  - [style.css](../frontend/src/style.css)：固定 `.ohlc-hud` 最小高度 `28px`、`.hud-forming-note` 右对齐与常规均线区位置一致，移除窄屏媒体查询中对 `.ohlc-hud` 的 `flex-wrap: wrap` 以消除高度跳动。
- **自动化测试、构建与 1440×810 盘中实盘复验。**
  - 全量 `pytest -q` **94 项通过**，`ruff check signaldesk tests` 全通过，CSS 全部 `243` 条 `font-size` 最小值为 `12.0px`，前端 `tsc -b && vite build` 构建通过（产物 `index-BSlXdylC.js`）。
  - 实盘 `1440×810` 浏览器终验：
    - `NVDA`「最新」（60 根）悬停最右侧 `2026-11-23` K 线（`x=961, y=571`）：不点击停留 4 秒（每秒采样）与**直接点击该 K 线后再停留 3 秒**，Tooltip 全程保持可见不消失（`tipLen = 133`）且内部现价（`166.02 → 165.99 → 166.02 → 166.05 → 166.04 → 166.02 → 166.01 → 165.38`）与 `.ohlc-hud` 同帧实时同步；
    - 图面核验：最右侧 `2026-11-23` 为实心锐利 K 线，仅底部 X 轴有 1 个蓝色 `2026-11-23` 浮标，`低低* $124.50` 胶囊向左收拢不遮挡最新 K 线和 Y 轴，3 窗格与 4 窗格（同时开启 `MACD + RSI`）全部标题与 Y 轴刻度零叠字；
    - `NVDA`「全部」（1001 根）主图价格轴下限修正为 `0.00`（消除 `-300.00` 负数），`x=962..966` 连续扫描 HUD 与 Tooltip 同步无错位（注：1001 根全历史下每根 K 线宽度不足 0.7px，最右侧第 1001 根位于整数像素边界 `966~967` 交界处，放大至「近1年 / 近6月 / 近3月 / 最新」即可宽裕精准点选）；
    - `ANT`（3 根短历史）与 `SQQQ` 回归验证均渲染正常、WS 推送期间 Tooltip 稳定；全程控制台 **0 errors**，`.error-fallback = 0`，`.chart-error-overlay = 0`。

## 2026-11-24 当日盘中实时 K 线展示与精简盘外动态结论卡

- **盘中实时 K 线接入（零污染正式收盘指标）。**
  - [providers.py](../signaldesk/providers.py) 在常规 `quotes()` 与 `_on_quote()` 同步提取当日 `open/high/low/volume/turnover`；[service.py](../signaldesk/service.py) 在同交易日内保持 `high = max` / `low = min` / `volume = max` 合并、跨交易日自动清零旧 OHLCV，并在 `detail_for()` 为美股盘中实盘追加标记 `intraday_forming = True` 的当日实时 K 线（不生成未收盘均线/MACD/RSI，不修改 `summary`/`wave_trend`/`forecast`）。
  - [Chart.tsx](../frontend/src/Chart.tsx) 接收 WebSocket 实时 `liveQuote` 原地刷新当日实时 K 线，HUD 显示 `2026-11-23 盘中` 胶囊与「开/高/低/现/量 · 盘中实时K线（指标以已收盘日线计）」，蜡烛与成交量柱采用半透明虚线区分，Tooltip 显式注明未收盘且不计入正式指标。
- **精简「盘外动态」结论卡。**
  - 重构 [StockInspector.tsx](../frontend/src/StockInspector.tsx) 的 `ExtendedHoursCard` 为紧凑结论卡（仅展示标题、状态胶囊与一句大白话结论，三段明细默认折叠于 `<details>` 内可按需展开）；常规盘中时段自动将「买卖评级与点位预测」置于右侧第 1 顺位、精简「盘外动态」收至其下方。
- **自动化测试、构建与 1440×810 盘中实盘复验。**
  - 新增 2 项盘中实时 K 线零污染与同日/跨日 OHLCV 合并单测，全量 `pytest -q` **94 项通过**，`ruff check signaldesk tests` 全通过，CSS 全部 `243` 条 `font-size` 最小值为 `12.0px`，前端 `tsc -b && vite build` 构建通过。
  - 美股盘中 `1440×810` 浏览器实盘核验（`http://127.0.0.1:8765/`）：顶栏确认自动选连 **`longbridge.cn`** 加速节点，左侧 `93` 只自选与整页 **0 处「待更新」**；`NVDA` 图面最右侧实时渲染 `2026-11-23` 盘中 K 线与放量成交量柱，HUD 实时跳动（`开 167.08 高 171.50 低 156.93 现 164.39 +30.95% 量 485.4M`）；右侧第 1 顺位为「买卖评级与点位预测」，第 2 顺位为折叠态精简「盘外动态」（`121px` 高，点击展开三段明细正常）；全程控制台 **0 errors**，7 个请求全部 HTTP `200`。

## 2026-11-24 非代理国内加速路由、秒出报价与盘中「待更新」根因修复

- **网络实测与根因定位。**
  - 实测本机连接长桥节点耗时：`longbridge.cn` 行情耗时 **`608 ms`**，较此前硬编码的 `longbridge.com`（**`2,560 ms`**）快 **4.2 倍**；美国财政部 `home.treasury.gov` 在弱网/直连下易 `ReadTimeout`；并确认造成界面长时间或反复显示「待更新」的三个直接原因：① `_connect()` 在拉取首次 `quotes()` 前串行逐只拉取 93 只标的 1,000 根历史日线阻塞 ~2 分钟；② 盘中实时 `PushQuote` 不含 `prev_close`，跨交易日时 `_quote()` 主动 `pop("prev_close")` 导致涨跌幅清空；③ 盘中 `_poll()` 每分钟串行轮询 93 只未收盘日线堵塞实时推送消费。
- **修复内容。**
  - [providers.py](../signaldesk/providers.py) 新增 `probe_fastest_broker_domain()`（端到端 TLS 握手测速，避免本机 TUN Fake-IP 代答 TCP ACK 误判）与同品牌 `.cn`/`.com` 白名单校验，[broker_oauth.py](../signaldesk/broker_oauth.py) 增加 `.cn` OAuth 网络故障容错回退，[research.py](../signaldesk/research.py) 为财政部接口增加单次网络重试。
  - [service.py](../signaldesk/service.py) 改造启动与轮询管线：实盘启动从 SQLite 已确认日线预填参考价与昨收（`_seed_quote_from_frame`）；`_connect()` 优先 1 秒内批量拉取全部 `quotes()` 再 `subscribe()` 并刷新估值，缺失日线与基准 ETF 交由后台 `Semaphore(5)` 异步补齐；盘中例行 `_poll(skip_synced_daily=True)` 自动跳过已对齐最近已完成交易日的标的；跨交易日无 `prev_close` 实时推送自动以本机已确认上一交易日收盘兜底并在 5 秒内快刷校对精确昨收；断连时自动排除故障节点切换同品牌备用网关。
- **自动化测试与实盘盘中核验。**
  - 新增 `tests/test_connectivity.py`（5 项测试），全量 `pytest -q` **92 项全部通过**，`ruff check signaldesk tests` 全通过，私密文件隔离测试通过。
  - 美股常规盘中实盘核验（`http://127.0.0.1:8765`）：左侧 `93` 只自选与整页 **0 处「待更新」**；`NVDA` 5 秒连续盘中推送（`$166.22 → $166.18 → $166.27 → $165.79`）涨跌幅稳定无闪回，右侧估值 `LongPort · 有效`；盘中自动抑制中栏 `.ext-hours-strip`，右侧 `.ext-card` 三段轨迹两行显示无省略号；控制台 **0 errors**，无 `4xx/5xx` 错误请求；并实测复验 TLS 握手探测在 TUN 环境下精准选中 `longbridge.cn`。
- **未验证项。** 彻底关闭代理软件 TUN 网卡后的纯运营商宽带 24 小时断线重连压测仍需在实际离线网络下观察；美国财政部 `home.treasury.gov` 无代理超时仍依赖 6 小时本机缓存降级。

## 2026-11-23 夜盘、盘前与盘后独立行情融合及流动性过滤跳空预警（方案 A）

- **LongPort 实盘接口实测。** 以只读方式启用 `enable_overnight=True` 并探测 `NVDA.US`/`AAPL.US`/`QQQ.US`/`SPY.US`/`TSLA.US`，核实账号可完整返回 `pre_market_quote`、`overnight_quote` 与 `post_market_quote`（含 `last_done`、`high`、`low`、`prev_close`、`volume`、`turnover`、`timestamp`，且三段 `prev_close` 均锚定最近常规收盘价）。
- **前后端实现与隔离设计。**
  - 新增 `signaldesk/extended_hours.py`（规则 `ext-1.0.0`），修改 `signaldesk/providers.py`（开启 `enable_overnight=True`、独立 `extended_quote` 推送通道、`quotes()` 提取三段盘外字段）、`signaldesk/service.py`（独立合并与乱序保护，绝不覆写常规 `last` 或触发常规盘止损事件）、`signaldesk/demo.py`（确定性合成盘外数据）、`signaldesk/security.py` 与 `signaldesk/codex_bridge.py`（白名单透传脱敏 `extended_hours` 并约束不可混同常规收盘）。
  - 严格流动性门控：盘外成交额 `< $100万` 标为「成交偏薄」并将高危预警强制降级为 `info`；放量盘外同步预检 `±3% / ±6%` 跳空及个人计划价、波浪失效/反转位与参考买卖点穿越；常规盘中自动抑制盘外实时预警。
  - 前端新增中栏单行 `.ext-hours-strip`（盘前/夜盘现价、跳空%、成交额/流动性、夜盘连续对比与异动徽章）、左侧列表「盘外异动」正交排序与按需单行盘外跳空提示、以及右侧「夜盘 / 盘前 / 盘后动态」卡片（展示三段轨迹、预警明细与隔离免责声明）。
- **自动化测试与构建。** 新增 `tests/test_extended_hours.py`（6 项测试，覆盖盘前优先于过期盘后/夜盘、薄流动性强制降级、放量触及止损/目标/波浪反转位预警、盘中抑制预警、乱序推送不覆盖常规主价及不污染日线评分与 5 级评级、API 与脱敏白名单隐私）；全量 `pytest -q` **87 项通过**（存在 1 条既有 Starlette httpx 兼容弃用提示）；`ruff check signaldesk tests` 全通过；`frontend/src/style.css` 全部 `238` 条 `font-size` 声明最小值为 `12.0px`；前端 `tsc -b && vite build` 生产构建通过。
- **16:9 浏览器实盘核验（`1440×810`，`http://127.0.0.1:8765` 盘前时段）。**
  - `NVDA` 中栏 `.ext-hours-strip` 严格单行（`699×33.2px`）实时呈现 `盘前 $136.50 +8.74% · 额 $5.90亿 · 放量充分 · 夜盘 $135.39 (+7.9%) · 盘前异动 1条`，下方 `.chart-panel-card` 保留 `428px` 高度；常规主价（`$125.53 / -14.01%`）、日线评分（`6.5分`）与 5 级评级（`谨慎减持 43.1分`）零污染。
  - 右侧 `.ext-card` 展示盘前/夜盘/盘后三段轨迹与跳空预警；发现 3 列小格内「百分比 + 成交额」同行出现轻微省略号截断，随即拆分为两行（涨跌幅行 + 成交额行）并将非当前段角标改为美东日期，重新构建确认彻底消除省略号。
  - 左侧切换「盘外异动」排序后按放量盘外跳空准确降序展示（`SOXS -18.5% / $2.42亿`、`SOXL +18.1% / $4.13亿`、`RAM +16.5% / $263万`、`MUU +14.0% / $1230万`、`SNXX +13.7% / $683万`），28 只「成交偏薄」标的自动排后并标「偏薄」，行内无溢出；全程控制台 **0 errors**，无 `4xx/5xx` 错误请求。
- **未验证项。** 常规盘中时段自动隐藏实时盘外预警条与盘后时段切换依赖实时交易时段推进（已由单元测试覆盖）；本轮未执行真实 Codex CLI 手动推理。

## 2026-11-23 宏观水位、流动性与「市场大势」面板（P0 数据底座 + P1 市场大势面板）

- **FRED 数据源实测与口径核验。**
  - 实测 FRED `fredgraph.csv?id=...` 公开直链免 API Key 可稳定拉取全部目标序列（`WALCL`、`WTREGEN`、`RRPONTSYD`、`WRESBAL`、`SOFR`、`IORB`、`NFCI`、`ANFCI`、`BAMLH0A0HYM2`、`BAA10Y`、`VIXCLS`、`DTWEXBGS`、`DFII10`、`T10Y3M`，均返回 HTTP `200`）。
  - 核实关键单位与窗口边界：`WALCL` / `WTREGEN` / `WRESBAL` 为**百万美元**（须 `÷ 1000`），`RRPONTSYD` 直接为**十亿美元**（严禁再除 `1000`）；`BAMLH0A0HYM2` 在 FRED 受 3 年授权限制（约 `794` 条），不足以算 10 年历史分位，故引擎在样本 `< 2,200` 时自动采用 40 年完整的 `BAA10Y` 计算 10 年因果分位并透明说明；核实纽约联储 `10Y-3M` 单变量 Probit 12 个月衰退概率公式 `Φ(-0.5333 - 0.6330 × spread)`。
- **前后端实现与隐私边界。**
  - 新增 `signaldesk/macro.py`（规则 `macro-1.0.0`）：严格按官方发布时刻截断（H.4.1 周四 16:30 ET、NFCI 次周周三 09:30 ET）、剔除缺失值 `.` 不前向填充、严格因果 10 年滚动分位；合成六分项指示灯、「流动性方向 × 指数趋势」四象限（顺风/背离/修复/逆风）、「红灯数 / 6」下行风险水位与联动警报；演示模式提供确定性离线合成宏观数据与 6 只基准 ETF 合成日线。
  - 升级 `signaldesk/research.py` 解析美国财政部 `BC_3MONTH`、计算 `10Y-3M` 利差与 NY Fed Probit 衰退概率，同时补充扣除通胀的 10Y TIPS 实际利率股债利差（`real_yield_gap_pp`）；保留 `treasury_observations()` 原二元组返回以完全向后兼容。
  - `signaldesk/service.py` 接入 `refresh_macro()` 独立 6 小时/15 分钟重试策略与独立只读缓存分区 `macro-live`（拉取 `SPY`/`QQQ`/`RSP`/`IWM`/`HYG`/`IEF` 基准日线，绝不写入或污染用户 `portfolio:live`）；第一阶段市场大势仅作底色展示，**不修改个股买卖评级**。
  - 新增 `GET /api/macro`，升级 `safe_snapshot()` 白名单透传脱敏 `macro_regime`（不含持仓/资金/账户标识），Codex 仍保持纯手动触发。
  - 前端新增 `frontend/src/MacroRegimePanel.tsx`（顶栏紧凑触发胶囊「大势·四象限 + 红灯 X/6」+ `createPortal` 全屏居中 960px 宽双标签全景弹窗「大势全景与六分项 / 口径与学术依据」），升级 `GuidePopover.tsx` 美债解读浮层与 `StockInspector.tsx` 个股实际利率利差展示。
- **自动化测试与构建。** 全量 `pytest -q` **81 项通过**（含新建 `tests/test_macro.py` 8 项测试，覆盖 CSV 缺失值不前向填充、H.4.1/NFCI 发布日对齐、净流动性单位换算与不跨周填充、严格因果分位、BAA10Y 回退与信用 `<10%` 过热黄灯、3M Probit 与实际利率利差、四象限与流动性螺旋/管道/倒挂解除警报、`/api/macro` 与脱敏白名单隐私及个股评级零干扰；存在 1 条既有 Starlette httpx 兼容弃用提示）；`ruff check signaldesk tests` 全通过；`frontend/src/style.css` 全部 `219` 条 `font-size` 声明最小值为 `12.0px`；前端 `tsc -b && vite build` 构建通过。
- **16:9 浏览器实盘核验（`1440×810` 亮色三栏，同步 93 只美股自选）。**
  - 顶栏 `.desk-topbar`（`1440×64`）中 `大势·逆风 红灯 3/6` 胶囊与 `美债2Y 4.63% / 10Y 4.92% / 10Y-2Y +29bp / 10Y近21日 -21bp` 严格单行无换行、无遮挡、无溢出。
  - 点击美债条展开解读浮层，正确展示 `10Y-3M +60bp · NY Fed 12M 衰退概率 18.1%`（3M `4.32%`）、`10Y 实际利率 2.88%` 及快捷入口；点击进入「市场大势与宏观流动性全景」弹窗，视口严格居中（`960×712.8`，左右各留 `240px`），实盘读数完整呈现 `逆风（3/6 红灯：绿2 黄1 红3）` 与六分项（①净流动性 `$5,825B` 且 `SOFR−IORB +1.0bp` 红灯及资金管道提醒、②`NFCI -0.48` 黄灯、③`HY OAS 3.52%` / `BAA10Y` 10 年分位 `10.5%` 绿灯、④`实际10Y 2.88%` 绿灯、⑤`SPY 相对 MA200 -5.9%` 红灯、⑥`VIX 28.44` 红灯），「口径与学术依据」Tab 完整无溢出；并顺手修正了进度条与明细在 `10.5%` 处的舍入显示一致性（统一保留 1 位小数）。
  - 右侧个股 `NVDA`「估值与美债对照」底部明确展示 `实际利率利差（减 10Y TIPS 2.88%）+4.60pp`；左侧自选池 93 只标的中 `RSP`/`IWM`/`HYG`/`IEF` 均未混入（仅用户自选原有的 `SPY`/`QQQ` 存在）；控制台 **0 errors**，无非 `200` HTTP 错误请求。
- **未验证项。** P2 阶段 ALFRED 历史版本回放与样本内外条件分布回测尚未实施（当前灯色阈值仍为基于文献的初版规则）；本轮未执行真实 Codex CLI 手动推理，未执行 24 小时断网压测。

## 2026-11-23 宏观水位、流动性与「市场大势」调研（仅文档）

- **范围。** 在 [docs/research.md](research.md) 新增宏观水位、流动性与市场大势调研（19 项文献证据地图、六分项 + 四象限面板草案、数据源与发布时间口径、不建议纳入项），在 [TODO.md](../TODO.md) 新增 P0–P3 路线图。本轮**未修改任何代码**。
- **验证。** 仅运行 `pytest tests/test_integrations.py -k test_no_private_runtime_files_tracked -q` 确认无运行时/私密文件进入跟踪区；因无代码改动，未重跑全量 pytest、Ruff 与前端构建。
- **未验证项。** 未实测 FRED `fredgraph.csv` 免 key 可用性、ICE 高收益 OAS 在 FRED 上的历史年限、长桥 VIX/指数行情可用性；文献结论来自公开摘要与检索综述，未逐篇核对全文；所有灯色阈值均为未回测草案。

## 2026-11-21 波浪理论一级简洁视图、明确波浪点位与二级参数说明弹窗

- **波浪板块分层与点位清晰化。**
  - 新建 `frontend/src/WaveTrendSection.tsx` 替换原冗长术语化卡片：一级窗口收敛为「一句话直观定位（浪型 + 通道位置）」「波浪各点位明细（节点标号、中文名称、形成日期、确切价位、相对前段涨跌幅与进行中标记）」「关键观察与测算点位（前高突破位、前低失效位/前高反转位、各条斐波那契测算位均标明确切价位与距现价%，并直接显示通道下/中/上轨数字）」与「一句话行动参考」。
  - 在卡片右上角与底部新增「详解与参数」二级弹窗（`WaveTrendGuideModal`），分三栏解释「当前参数与校验（通道分位、20日斜率、通道边界、ATR 因果反转阈值、道氏高低结构、均线排列与已通过的艾略特铁律）」「波浪与点位怎么看（四大关键点位与 ATR 参考止损区别 + 0–5 / A-C 浪与 `*` 虚线含义）」「斐波那契与纪律（0.618 / 1.0 / 1.618 与顺势通道原则）」。
  - `frontend/src/Chart.tsx` 主图波浪胶囊同步显示确切价位（如 `起 $36.20`、`1浪 $49.63`、`2浪 $39.53`、`3浪* $58.43`），并配合 `labelLayout: { hideOverlap: true }` 避免叠压；`signaldesk/wave_trend.py` 文案术语统一为「前低失效位」。
- **自动化测试与构建。** 全量 `pytest -q` **73 passed**，`ruff check signaldesk tests` 通过，`frontend/src/style.css` 全部 `193` 条 `font-size` 最小值为 `12.0px`；`tsc -b && vite build` 通过。
- **16:9 浏览器实盘核验与精修（`1440×810`）。** 首轮实测发现二级弹窗因右侧卡片层叠上下文被限制在 340px 右栏内、标题「通道上/中/下轨」与数值（下/中/上）顺序相反，以及 `SQQQ` 图面 `起 $36.20` 与 `2浪 $39.53` 胶囊叠压；随即使用 `createPortal(..., document.body)` 挂载弹窗至全屏视口居中（680px 宽）、修正标题为「通道下 / 中 / 上轨」、精简进行中浪名并采用相邻同侧拐点错位 + ECharts `labelLayout: { moveOverlap: "shiftY" }` 防重叠，重新构建并复测通过，控制台 **0 errors**。

## 2026-11-21 防白屏稳定性加固与 ETF/指数基金专属分析框架

- **白屏排查与稳定性修复。**
  - 根因定位：前端全局缺少 React `ErrorBoundary`（React 19 在渲染或 `useEffect` 抛异常时会直接卸载整棵树变为纯白屏）；实盘 92 只标的未缓存 `wave_trend`/`forecast`，导致每次 `Monitor.snapshot()` 阻塞主事件循环 `670.9 ms` 并每 2 秒向浏览器无条件推送 `~660 KB` 重复 JSON；`index.html` 缺少 `Cache-Control: no-store` 易在重新构建前端后因缓存旧 HTML 请求已删旧 hash JS 造成白屏；`Chart.tsx` 缺少 `dates` 非法时间、`zoom.start/end` 非有限数、`0×0` 容器 resize 与 `setOption` 异常保护，多处组件缺少深层字段空值防御。
  - 修复落地：新增 `frontend/src/ErrorBoundary.tsx` 包裹顶层 `<App />` 及左/中（K线）/右三块区域；加固 `Chart.tsx`、`App.tsx`、`WatchlistRail.tsx`、`StockInspector.tsx`、`Settings.tsx` 与 `types.ts`（WebSocket 载荷校验 + 非 JSON 报错兼容）；后端 `Monitor` 在 `rebuild()` 中缓存 `wave_trend`/`fund_metrics` 并按指纹缓存 `forecast`（92 只实盘标的稳态 `stocks()` 耗时由 `670.9 ms` 降至 **`16.5 ms`**，提速 40 倍），`/api/stream` 改为按业务指纹去重推送（静止时 20 秒心跳）并递归清洗非有限浮点（`_sanitize_json` + `allow_nan=False`），`GET /` 返回的 `index.html` 显式增加 `Cache-Control: no-cache, no-store, must-revalidate`。
- **ETF/指数基金与个股分流分析。**
  - 实盘核查确认券商 `calc_indexes` 对基金主体返回的 PE/PB 严重失真（如 `QQQ` `-6.88x` 被误判为「亏损警示 / 建议卖出」、`SOXX` `0.79x` 被算出 `126.6%` 假盈利收益率、`GLD`/`SLV`/`USO` 商品信托无公司盈利却被套算股债利差、`SQQQ`/`YANG` 3X 反向做空 ETF 被打出「建议买入」）。
  - 新增 `signaldesk/instruments.py`（精确代码映射 + 名称/组合规则），实盘 92 只标的自动区分为 **27 只 ETF/基金** 与 **65 只个股**；对 ETF/基金自动停用公司 PE/PB 与「亏损警示」，改用严格因果的 52 周高点回撤、近 1 年价格分位、20/60 日年化波动率、近 1 年最大回撤与 10Y 美债 21 日变动评估；反向做空杠杆 ETF 启用「对冲观察」与评级封顶 `hold` 护栏，正向高倍杠杆 ETF 封顶 `buy` 并附波动复利损耗警示；右侧自动切换为「基金与指数特征」卡片；`safe_snapshot()` 与 Codex prompt 同步隔离失真基金 PE 并切换基金复核口径；顺便排查到 `SOXX` 在 `2026-11-05` 存在一次不复权拆股跳空（`450.41 → 131.90`，`-70.7%`），已记录在说明文档中。
- **自动化测试与构建。** 全量 pytest **73 项通过**（含新建 `tests/test_instruments.py` 7 项测试，存在 1 条既有 Starlette httpx 兼容弃用提示）；`ruff check signaldesk tests` 全通过；`test_no_private_runtime_files_tracked` 通过；`frontend/src/style.css` 全部 `163` 条 `font-size` 声明最小值为 `12.0px`；前端 `tsc -b && vite build` 通过。
- **16:9 浏览器实盘核验（`1440×810` 亮色三栏，同步 92 只美股自选）。**
  - 页面加载、切换 `QQQ`/`SOXX`/`SQQQ`/`NVDA`/`ANT`（2 根极短 K 线）及反复开关 `RSI`/`MACD` 全程无白屏、控制台 **0 errors**、无 `4xx/5xx` 失败请求。
  - `QQQ` 正常显示「宽基指数 ETF」、第二支柱「回撤波动」与右侧「基金与指数特征」（追踪纳斯达克 100、回撤 `-20.2%`、分位 `26%`、60日波动 `27.4%`、最大回撤 `-19.9%`），不再有「亏损警示」或公司财报话术；`SOXX` 显示「行业主题 ETF」与半导体基金特征，不再出现 `0.79x PE`；`SQQQ` 显示「3X 反向 ETF」、行动标签「对冲观察」、风控护栏封顶「中性观望」与反向波动损耗警示条；`NVDA` 对照个股仍正常显示「估值与美债对照」；并同步过滤 `.stock-hero` 中冗余的 `us` 市场分组胶囊、精简反向 ETF 副标题，以及将主图波浪摘要中易混淆的「防守 $xx」升级为按方向直译的「破前低 $xx 失效 / 站上前高 $xx 反转」可点击说明胶囊（点击可看拐点来源日期、浪号及与左侧 ATR「参考止损」的区别），同时扩充 `signaldesk/instruments.py` 中英文通用 ETF 分类规则以自动覆盖任意未入表新标的。
- **未验证项。** 本轮未执行真实 Codex CLI 手动分析推理；未对照长桥 App 同屏历史逐笔读数；未执行 24 小时持续挂机与断网恢复压测；不复权拆股（如 `SOXX 2026-11-05`）的自动前复权切换留待后续按需评估。

## 2026-11-21 16:9 界面精简、大白话状态标签与波浪趋势 K 线可视化

- **功能与界面变更。**
  - 新增 `frontend/src/GuidePopover.tsx`：顶栏美债利率条改为可点击按钮并弹出实时大白话解读卡片（美债 2Y/10Y、10Y-2Y 期限利差、10Y 近 21 日变动与对美股估值影响）；K 线工具栏右侧新增 `? 指标` 二级分类菜单（「均线与布林」「MACD与RSI」「波浪与趋势」「点位与评分」），并在右侧原始技术算子列表中补充悬浮说明；`.stock-hero` 自动过滤 `all`/`全部`/`全部自选` 等无意义系统分组胶囊。
  - 按用户反馈精简左侧自选列表：移除无用的 `.source-pill`（`自选·us`）胶囊以完整显示公司名称；将后端 `verdict` 行动标签升级为大白话（`跌破止损`、`触及目标`、`仓位待核`、`亏损警示`、`转弱警惕`、`关注买点`、`趋势向好`、`持有观察`、`弱势观望`、`震荡观望`、`数据不足`），补充 `action_meaning` 悬浮释义，并在左侧排序栏新增可收起的「标签说明」图例卡片；将原本重叠混乱的 6 项排序精简为 4 项正交排序（默认 `买卖评级`、`风险预警`、`今日涨幅`、`今日跌幅`）。
  - 默认关闭 `RSI` 副图（`showRsi = false`，工具栏可随时一键开启），按 16:9 比例将主 K 线窗格扩展至 `58%` 高度并留足上下安全边距（`top: 32`、`boundaryGap: ["10%", "12%"]`），同时将预测点位文字标注移至左侧空白区（`insideStartTop`），把右侧视野完全让给最新 K 线与波浪标号。
  - 新增严格因果波浪与趋势分析引擎 `signaldesk/wave_trend.py`（`compute_wave_trend()`）：基于 ATR 自适应因果拐点识别道氏结构（`HH/HL/LH/LL`）、拟合近 90 日线性回归平行趋势通道、遵循艾略特波浪铁律识别 1–5 浪推动与 A-B-C 调整并测算斐波那契目标位，未形成标准浪型时诚实降级为「结构整理」不强行标浪；接入 `Monitor.stock()` 与 `safe_snapshot()` 隐私白名单；在 K 线主图叠加平行趋势通道、波浪折线、胶囊标号与顶栏单行状态摘要，并在右侧「综合研判」新增「波浪与趋势结构」卡片。
- **自动化测试与构建。** 全量 pytest **66 项通过**（含新建 `tests/test_wave_trend.py` 5 项因果/5 浪推动/ABC 调整/通道单调/缺数据降级测试、更新后的 `tests/test_long_research.py` 与 `tests/test_api.py` 隐私白名单断言；存在 1 条既有 Starlette httpx 兼容弃用提示）；`ruff check signaldesk tests` 全通过；`frontend/src/style.css` 正则检查全部 `148` 条 `font-size` 声明最小值为 `12.0px`；前端 `tsc -b` 与 `vite build`（沙箱外执行绕过 Windows `realpath EPERM`）构建通过（5.03s，产出 `index-BpZt9579.js`、`index-C4O8RbIv.css`）。
- **16:9 浏览器实盘核对（`1440×810` 亮色三栏，同步 92 只美股自选）。**
  - 左侧列表无任何 `.source-pill` 残留，点击「标签说明」展开/收起正常，各行大白话标签与悬浮 `title` 完整；`.stock-hero`、`.forecast-strip`、`.chart-toolbar`（`RSI` 默认未激活，`MACD`/`点位`/`波浪` 默认开启）与 `.ohlc-hud` 均保持严格单行无截断。
  - `NVDA` 展示红色虚线下降通道、波浪轨迹、`高抬/低抬/高低/低低*` 胶囊与「下降趋势 · 结构整理 · 跌破通道下轨 · 防守 $243.37」；`KO` 展示绿色虚线上升通道、`起 / 1浪 / 2浪*` 胶囊、左侧对齐的 `目标卖点`/`参考卖点`/`参考买点`/`参考止损`（与顶栏和右侧波浪零遮挡），右侧「波浪与趋势结构」卡片中 `突破确认`/`反转阻力`/`结构防守` 单行无折字且无横向溢出；控制台 **0 errors**，全部 8 个资源/API 请求均返回 HTTP **200**。
- **未验证项。** 本轮未执行真实 Codex CLI 手动分析推理；未对照长桥 App 同屏历史逐笔读数；未执行 24 小时断网与长时间挂机监控压测。

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
