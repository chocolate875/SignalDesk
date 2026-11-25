# AGENTS.md — SignalDesk 协作、架构交接与工程规范

本文件为所有接手维护本仓库的开发者与 AI 编码智能体（Google Antigravity / Codex / Claude 等）提供完整的**架构交接图谱、接口继承契约、安全红线、视觉规范以及环境/Git 标准操作流程**。

---

## 1. 项目定位与环境栈

- **定位**：本地优先（Local-First）的美股长期持仓与自选股桌面复核工作台。结合宏观流动性与美债曲线、个股估值/ETF 特征、前复权日线、严格因果学术因子（`fusion-2.0.0`）、动态风险预算以及手动触发的**本地官方多 Agent 复核（Google Antigravity ACP / OpenAI Codex exec）**辅助长期决策。
- **后端栈**：Python `3.12+`（强制由 **`uv`** 统一管理环境与锁文件 `uv.lock`），FastAPI + Uvicorn + WebSocket + SQLite（WAL 模式）+ `longbridge`（仅只读接口）+ `pandas` / `numpy` / `ta==0.11.0` + `exchange-calendars` + `httpx` + `pydantic` v2。
- **前端栈**：React 19 + TypeScript 5.7 + Vite 6 + ECharts 6 + Lucide Icons（位于 `frontend/`，由 `package-lock.json` 锁定）。生产构建输出至 `frontend/dist/`（不入 Git，首次启动或开发构建自动生成），由 FastAPI 直接托管静态资源，零外部 CDN 依赖。

---

## 2. 核心模块拓扑与接口契约（交接字典）

### 2.1 后端模块（`signaldesk/`）

| 模块 | 职责与核心契约 | 关键依赖 / 状态边界 |
|---|---|---|
| `models.py` | 全量 Pydantic 数据契约，继承自 `StrictModel(extra="forbid")` | 新增持久化字段**必须**带向后兼容默认值，严禁破坏既有 SQLite `kv` 反序列化 |
| `security.py` | 本机数据目录定位、DPAPI/Fernet `Vault` 凭据库、会话令牌、`safe_child_environment()` 与 **`safe_snapshot()` 白名单** | 严禁将 `broker_quantity`、`cost_price`、`available_quantity`、`net_assets` 或任何密钥放行出白名单 |
| `storage.py` | 线程安全 SQLite WAL 存储（`kv`、`bars`、`events`、`outbox`、`analyses`） | 前复权日线桶为 `live-fwd-v3` 与 `macro-live-fwd-v3`；拆股重对齐走原子 `replace_bars()` |
| `providers.py` | `LongPortFeed`（长桥只读行情/持仓/自选/前复权日线/估值/换手市值）及 `.cn`/`.com` 网关自动测速择优 | **绝对只读**，严禁添加任何交易/下单/改自选接口 |
| `calendar.py` | `XNYS` 纽交所交易日历、半日盘保守边界、K 线结束时间与会话判定 | 所有时间统一基于带时区 `datetime` 计算 |
| `operators.py` | 11 个确定性历史滚动白名单算子（`delay`、`delta`、`returns`、`mean`、`std`、`clip` 等） | 仅允许正整数历史窗口，严禁 `eval` 或任意代码执行 |
| `indicators.py` | `RULE_VERSION = "fusion-2.0.0"` 日线/分时指标富化（`enrich`）与三维平滑评分（`summarize`） | 默认权重 `45% 趋势 + 40% 动量 + 15% 10日量价顺向度`；缺交易日断档自动切断预热 |
| `factors.py` | 严格因果学术因子引擎（`compute_academic_factors`、`compute_yang_zhang_hv`） | 残差动量（扣 `SPY` Beta 不扣自身 Alpha）、FIP `info_discreteness`、52W 高点比、日夜拉锯、MAX5、下行 Beta、偏度、Amihud |
| `factor_eval.py` | CLI 离线横截面因果回放评测工具（`uv run signaldesk-eval`） | 只读扫描 `bars` 表计算未来 5/20/60d RankIC、共线性矩阵与移动止损回撤对比 |
| `instruments.py` | 证券资产分类（正股 vs 宽基/行业/商品/杠杆反向 ETF）与基金专属特征计算 | ETF 自动屏蔽失真的基金主体 PE/PB，改用回撤分位与 Yang-Zhang 波动率 |
| `wave_trend.py` | 严格因果 ATR ZigZag 摆动拐点、线性回归平行趋势通道与艾略特波浪铁律校验 | 未确认末端拐点显式标记 `confirmed = False` |
| `extended_hours.py` | `ext-1.0.0` 夜盘/盘前/盘后独立行情汇总、`$100万` 流动性门控与近 20 日隔夜/盘中拉锯预警 | 绝不污染常规盘 `quote["last"]`、日线指标或正式收盘评级 |
| `macro.py` | `macro-1.0.0` 14 条公开 FRED 序列发布时间对齐、六分项指示灯与四象限风险环境底色 | 基准 ETF 存于独立 `macro-live-fwd-v3`，不混入用户自选池 |
| `research.py` | 美国财政部 `3M/2Y/10Y` 国债曲线、NY Fed 衰退 Probit 概率与名义/TIPS 实际股债利差 | 估值超 4 天或利率超 7 天自动标为过期 |
| `forecast.py` | 去重锚点买卖区间测算、正交四维 5 级综合评级、风控封顶护栏与 `risk_budget`（参考敞口 + 60日 `trailing_stop`） | 强制满足严格单调价格关系 `0 < stop_loss < buy_low < buy_high <= close < sell_low < sell_high` |
| `agent_bridge.py` | **`OfficialAgentBridge` 协议接口**、Google Antigravity 官方 `agy acp`（ACP v1 JSON-RPC over stdio）客户端与多引擎协调器 `AgentHub` | 新增任何本地 Agent 必须实现 `OfficialAgentBridge` 且**仅限官方原生协议**；ACP 握手强制关闭读写/终端并自动拒绝一切 `session/request_permission` |
| `codex_bridge.py` | 实现 `OfficialAgentBridge` 协议的 OpenAI 官方 `codex exec --output-schema` 桥接器 | 最小目录只读隔离运行，不使用第三方非官方 `codex-acp` 包装器 |
| `events.py` / `notifications.py` | 状态转移事件去重冷却、本机桌面通知与 QQ 官方机器人出站通道 | 风险告警不被机会过滤器吞没；QQ 消息经 `qq_text()` 白名单脱敏 |
| `service.py` | 核心协调器 `Monitor`（行情生命周期、拆股自愈、衍生缓存管理、`live_evaluation_for` 实时试算与 `snapshot` 聚合） | `rebuild()` 与 `_sync_macro_benchmarks()` 必须同步清理 `academic_factors`、`forecast_cache` 与 `live_eval_cache` |
| `app.py` / `desktop.py` / `launcher.py` | FastAPI 路由与本地 Origin/Session 鉴权、Windows 托盘驻留及启停进程管理 | 仅监听 `127.0.0.1` |

### 2.2 前端模块（`frontend/src/`）

- `App.tsx`：全局状态、WebSocket 增量订阅、「收盘确认 ↔ 最新行情试算」单一派生真相源（`effectiveStock`）、多 Agent 触发与脱敏预览弹窗。
- `WatchlistRail.tsx`：左栏分组/收藏筛选、评级与异动排序、状态标签图例。
- `Chart.tsx`：ECharts 多窗格前复权 K 线、当日盘中实时 K 线增量刷新（`notMerge: false` 防 Tooltip 闪烁）、平行趋势通道、波浪折线与买卖点参考线。
- `StockInspector.tsx` + `inspectorModules.ts`：右栏三标签页（「综合研判」7 大模块支持自定义显隐与拖拽排序持久化至 `localStorage`、「AI 复核」双官方 Agent 切换面板、「提醒动态」）。
- `WaveTrendSection.tsx` / `MacroRegimePanel.tsx` / `GuidePopover.tsx` / `Settings.tsx` / `ErrorBoundary.tsx`：趋势波浪卡、宏观全景弹窗、指标与美债二级解读浮层、系统与多 Agent 设置、三级容错边界。

---

## 3. 五大工程与安全红线（不可逾越）

1. **严格只读，绝不下单**：严禁向券商适配器添加任何下单、撤单、改仓或修改远端自选列表的写操作。
2. **零隐私泄露**：任何出站通道（本地 Agent CLI 子进程、预览接口、QQ 通知、日志与异常提示）严禁出现账户标识、持仓股数、成本价、资产金额或原始密钥；子进程环境必须走 `safe_child_environment()`。
3. **官方协议唯一性**：多 Agent 模块**仅允许官方公开支持的原生调用方式**（如 Antigravity 官方 `agy acp`、OpenAI 官方 `codex exec`）。严禁引入非官方第三方桥接器、屏幕抓取、伪终端模拟按键或逆向私有接口；所有 Agent 复核强制为纯手动触发（`automatic = False`）。
4. **严格因果与诚实降级**：一切指标、波浪拐点、学术因子与回放评测严禁使用未来数据、前向填充缺失 K 线或将零值冒充有效值；样本不足时必须诚实返回 `available = False` / `unavailable`。
5. **配置与数据库平滑兼容**：修改 `models.py` 时须确保旧版 `~/.local` / `%LOCALAPPDATA%\SignalDesk` 中的持久化 JSON 无需手工删库即可无损加载。

---

## 4. UI 视觉规范与前端自检

修改 `frontend/src/` 时检查视觉层级、色彩、键盘焦点、表单和弹层语义、React 组件组合及 reduced-motion 支持。本机已安装的设计技能可辅助自检，`.agents/skills/` 由 Git 忽略。

- **色彩与质感**：默认亮色「企业简洁风」（保留深色与跟随系统、红绿涨跌色切换）。画布底色 `#f8fafc`，白卡 `#ffffff` 配 `1px solid #e5e7eb` 与 `12px` 圆角；主色 `#1e40af`（Corporate Blue），焦点色 `#3b82f6`。
- **字号硬底线**：**全站 CSS 严禁出现任何 `< 12.0px` 的 `font-size`**（每次改动样式后必须运行下方字号审计命令确认 `bad = 0`）；金融数字统一启用 `font-variant-numeric: tabular-nums`。
- **16:9 信息分层**：一级视图聚焦核心结论、关键点位与紧凑网格，长篇点位依据、护栏细则、波浪历史拐点与免责声明统一收纳进 `<details>` 二级折叠区或说明弹窗，确保 `1440×810` 与 `1280×720` 下零横向溢出、零按钮挤压裁切。

---

## 5. 环境管理（`uv`）、验证与 Git 交付纪律

### 5.1 标准开发与验证命令（在仓库根目录 `SignalDesk/` 下执行）

```powershell
# 1. 同步锁定的 Python 3.12+ 虚拟环境（含 pytest / ruff 开发依赖）
uv sync --frozen

# 2. 后端代码规范与全量单元测试
uv run ruff check signaldesk tests
uv run pytest -q

# 3. CSS 最小字号合规审计（必须输出 bad=0）
uv run python -c "import re, pathlib; text=pathlib.Path('frontend/src/style.css').read_text(encoding='utf-8'); vals=[float(m.group(1)) for m in re.finditer(r'font-size\s*:\s*([0-9.]+)px', text)]; bad=[v for v in vals if v < 12.0]; print(f'total={len(vals)}, min={min(vals) if vals else 0}px, bad={len(bad)}')"

# 4. 前端类型检查与生产构建
Set-Location frontend
npm ci
npm run build
Set-Location ..

# 5. 启动无界面本机服务（或双击 Start-SignalDesk.cmd）
uv run signaldesk --headless --port 8765
```

### 5.2 文档与 Git 连续性纪律

1. 每次完成功能、口径或 UI 变更后，同步更新 [README.md](README.md)、[TODO.md](TODO.md)、[docs/signals.md](docs/signals.md) 与 [docs/verification.md](docs/verification.md)。
2. 提交前运行 `git status --short` 与 `uv run pytest tests/test_integrations.py -k test_no_private_runtime_files_tracked -q`，确保 `.runtime/`、`data/`、`*.sqlite*`、`*.encrypted`、`**/codex-exports/`、`**/agent-exports/`、`frontend/dist/`、`.env` 等绝不进入 Git 追踪区。
3. 提交和 PR 标题统一使用 `类型(范围): 中文摘要`，正文用中文说明原因与验证。日常任务从 `develop` 建分支，发布目标为 `main`。分支流向、示例和初始化命令见 [CONTRIBUTING.md](CONTRIBUTING.md)。
4. **仅在用户明确授权推送时执行 `git push`。**
