# SignalDesk 工程交接、Git 远程发布清单与待续开发指南

生成时间：2026-11-24  
仓库根目录：`SignalDesk/`（独立 Git 仓库，当前分支 `main`）  
当前状态：**开发已按指令安全暂停，工作区干净，全量 108 项自动化测试通过，随时可推送远程仓库或无缝恢复开发。**

---

## 一、当前完成基线总览

1. **量化与风控引擎（`fusion-2.0.0` + `macro-1.0.0` + `ext-1.0.0`）**
   - 完成本机 75 只非杠杆美股 / 9,307 截面严格因果回放实证（[factor_eval.py](../signaldesk/factor_eval.py)、[research.md](research.md)），剔除高共线短窗口指标（`zscore20/rank20/corr20`），升级为 `45% 趋势 + 40% 动量 + 15% 10日平滑量价顺向度`；
   - 上线 6 组零付费严格因果学术因子（[factors.py](../signaldesk/factors.py)：vs `SPY` 残差动量信息比、FIP 趋势连续度、52W 高点比、Yang-Zhang 20/60 日无偏波动率、下行 Beta、近月 `MAX5` 彩票过热，以及偏度、`Amihud` 冲击与换手率/总市值）；
   - 上线前复权日线自愈（`live-fwd-v3`）、「收盘确认 ↔ 最新行情试算」双口径预览、盘外独立通道与近 20 日隔夜/盘中拉锯预警（`tug_of_war`）、以及宏观联动 `risk_budget`（参考敞口系数 + 60 日峰值 `2.5×ATR14` 移动保护位）。
2. **本地官方多 Agent 长期复核架构（`OfficialAgentBridge`）**
   - 在 [agent_bridge.py](../signaldesk/agent_bridge.py) 定义运行时可校验的 `@runtime_checkable class OfficialAgentBridge(Protocol)` 协议契约与 `AgentHub` 注册表；
   - **Google Antigravity CLI（`antigravity`）**：严格按官方文档实现 `agy acp`（Agent Client Protocol v1，JSON-RPC 2.0 over `stdio`：`initialize` → `session/new` → `session/prompt`），握手显式关闭客户端读写与终端能力，并自动拒绝一切 `session/request_permission`；
   - **OpenAI Codex CLI（`codex`）**：经核查保持官方原生 `codex exec --output-schema` 最小目录只读隔离运行（不引入第三方非官方 `codex-acp` 适配器）；API 层对任何非官方 Agent 参数严格返回 HTTP `422`。
3. **16:9 企业简洁风界面与前端设计技能体系**
   - 补齐多格式品牌图标（`favicon.svg` / `.ico` / `apple-touch-icon.png`），右侧研判栏重构为 7 个可自定义显隐与拖拽排序的独立模块（[inspectorModules.ts](../frontend/src/inspectorModules.ts)）；
   - 全量 `288` 处 CSS `font-size` 最小值保持 `12.0px`（`bad = 0`）；
   - 项目内置 4 套前端设计与 React 19 工程规范技能于 [`.agents/skills/`](../.agents/skills)（`frontend-design`、`web-design-guidelines`、`vercel-composition-patterns`、`emil-design-eng`）。

---

## 二、环境管理方案（确认采用 `uv` + `npm ci` 双锁机制）

对于本项目的 Python `3.12+` 后端（含科学计算 `numpy/pandas/ta`、Web 服务 `fastapi/uvicorn` 与券商 `longbridge` C 扩展），**使用 `uv` 是最优且最稳健的环境管理方案**：

- **版本与依赖三重锁定**：
  - [`.python-version`](../.python-version)：锁定 Python `3.12`，防止新机器默认拉取过高实验版本导致二进制 wheel 缺失；
  - [`pyproject.toml`](../pyproject.toml) + [`uv.lock`](../uv.lock)：精确锁定全部 44 个 Python 包版本与跨平台哈希，并提供 3 个标准 CLI 入口（`signaldesk`、`signaldesk-replay`、`signaldesk-eval`）；
  - [`frontend/package.json`](../frontend/package.json) + [`frontend/package-lock.json`](../frontend/package-lock.json)：锁定前端构建树。
- **新机器克隆后一键复现流程**：
  ```powershell
  # 方式 A：全自动初始化脚本（安装 uv 锁定依赖 + npm ci + 构建前端静态包）
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
  .\Start-SignalDesk.cmd

  # 方式 B：开发者手动命令
  uv sync --frozen
  uv run ruff check signaldesk tests
  uv run pytest -q
  cd frontend && npm ci && npm run build
  ```

---

## 三、Git 远程同步文件完整清单与上传前安全审计

### 1. 受 Git 追踪的同步文件分类清单（共 103 个文件）

| 目录 / 类别 | 文件数 | 包含内容说明 |
|---|---:|---|
| **根目录工程配置与启停脚本** | 11 | `.env.example`、`.gitattributes`、`.gitignore`、`.python-version`、`pyproject.toml`、`uv.lock`、`AGENTS.md`、`README.md`、`TODO.md`、`Start-SignalDesk.cmd`、`Stop-SignalDesk.cmd` |
| **自动化初始化脚本（`scripts/`）** | 1 | `scripts/setup.ps1` |
| **Python 后端核心包（`signaldesk/`）** | 28 | `__init__.py`、`agent_bridge.py`、`app.py`、`broker_oauth.py`、`calendar.py`、`codex_bridge.py`、`demo.py`、`desktop.py`、`events.py`、`extended_hours.py`、`factor_eval.py`、`factors.py`、`forecast.py`、`indicators.py`、`instruments.py`、`launcher.py`、`macro.py`、`models.py`、`notifications.py`、`operators.py`、`providers.py`、`replay.py`、`research.py`、`security.py`、`service.py`、`startup.py`、`storage.py`、`wave_trend.py` |
| **前端工程源码（`frontend/`）** | 21 | `index.html`、`package.json`、`package-lock.json`、`tsconfig.json`、`vite.config.js`、`public/` 下 3 个品牌图标、`src/` 下 13 个 TS/TSX/CSS 源码文件 |
| **自动化测试套件（`tests/`）** | 18 | 覆盖因果指标、学术因子、波浪、点位、ETF 分类、拆股与实时试算、宏观、盘外、OAuth、安全隔离与多 Agent ACP 协议的 18 个测试模块（共 108 项用例） |
| **架构、口径与交接文档（`docs/`）** | 5 | `signals.md`、`research.md`、`research_todo.md`、`verification.md`、`handover.md`（本文档） |
| **项目级前端设计技能（`.agents/skills/`）** | 19 | `frontend-design`、`web-design-guidelines`、`vercel-composition-patterns`、`emil-design-eng` 规范文档 |

### 2. 已严格排除（不进 Git）的本地私密与构建路径（`.gitignore` 已验证）

- **私密凭据与实盘状态**：`.env`、`*.encrypted`、`**/credentials/`、`*.db`、`*.sqlite*`、`.runtime/`、`data/`、`logs/`、`**/codex-exports/`、`**/agent-exports/`（且实盘默认存于仓库外的 `%LOCALAPPDATA%\SignalDesk`）；
- **本地虚拟环境与构建缓存**：`.venv/`、`frontend/node_modules/`、`frontend/dist/`、`__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`output/`、`.playwright-cli/`（仓库内历史遗留的未追踪 `output/` 与 `.playwright-cli/` 临时截图目录已清理完毕）。

### 3. 全仓库与历史提交敏感信息扫描结论

- 对全部追踪文件及完整 `git log -p --all` 提交历史执行正则扫描：**0 处 API Key / Token / 私钥泄露，0 处本机个人绝对路径硬编码，0 处真实券商持仓股数/成本/资金泄露**；
- **上传前唯一人工确认项**：历史 Git Commit 的作者元信息为 `Choco <2251094944@qq.com>`。若推送到私有仓库无需任何处理；若推送到完全公开的 GitHub 仓库且不希望公开个人 QQ 邮箱，可在推送前决定是否保留或重写作者邮箱。
- **推送远程仓库参考命令**（由仓库持有人按需执行）：
  ```powershell
  Set-Location D:\Work\Code\Finance\SignalDesk
  git remote add origin <你的远程仓库URL>
  git push -u origin main
  ```

---

## 四、已暂停待续任务：5 项用户批注与前端优化精准实施指南（恢复开发第一步）

以下为用户在实盘看板批注的 5 项体验优化，**前期代码行号定位与数据源实测已全部完成**，下一个开发会话可直接按此清单编码落地（实施时请先阅读 `.agents/skills/` 下的 `frontend-design`、`web-design-guidelines`、`vercel-composition-patterns` 与 `emil-design-eng` 规范，保持当前亮色企业简洁风基调）：

### 1. K 线默认时间范围改为「近6月」
- **目标文件**：[`frontend/src/Chart.tsx`](../frontend/src/Chart.tsx)
- **精确位置**：
  - 第 `439` 行：`const [activeRange, setActiveRange] = useState<number>(252);` → 改为 `126`（提取常量 `const DEFAULT_RANGE_BARS = 126;`）；
  - 第 `757` 行与第 `760` 行：切股初始化 `setActiveRange(252)` 与 `let left = Math.max(0, rows.length - 252);` → 统一改为 `DEFAULT_RANGE_BARS`（`126`）。

### 2. K 线默认不开启 `MACD` 副图
- **目标文件**：[`frontend/src/Chart.tsx`](../frontend/src/Chart.tsx)
- **精确位置**：
  - 第 `434` 行：`const [showMacd, setShowMacd] = useState(true);` → 改为 `false`（与 `showRsi = false` 一致，默认仅开启「日线价格 + 成交量」2 窗格，主图纵向空间最大化，用户可随时点击工具栏 `MACD` 按钮开启）；
  - 同步更新 [`GuidePopover.tsx`](../frontend/src/GuidePopover.tsx) 中 `MACD` 说明标签标注为 `默认关闭`。

### 3. 消除顶栏「更多」菜单与外部按钮的功能重复
- **目标文件**：[`frontend/src/App.tsx`](../frontend/src/App.tsx)（`TopbarMoreMenu`，约第 `320–418` 行）
- **问题定位**：
  - 顶栏左侧 `.status-pill-merged` 已展示实时连接状态，「更多」内顶部的 `实时流已连接` 属重复；
  - 顶栏中部已有 `MacroRegimeTrigger` 与 `MacroStripWithGuide` 直达入口，「更多」底部的 `市场大势与美债全景 -> 打开`（第 `399–413` 行）属完全重复；
  - 外观主题按钮按第 4 项外置到顶栏后，也从「更多」中移除；
- **精简后「更多」定位**：收敛为清爽无重复的二级辅助面板（仅保留：北京/纽约双时钟、红涨绿跌/绿涨红跌配色切换、通知投递记录）。

### 4. 外观深浅色切换外置到顶栏，并支持「跟随系统」三态
- **目标文件**：[`frontend/src/App.tsx`](../frontend/src/App.tsx)（约第 `424–470`、`883–910` 行）与 [`frontend/src/style.css`](../frontend/src/style.css)
- **实现要点**：
  - 新增类型 `ThemeMode = "light" | "dark" | "system"`（`localStorage` 键如 `sd-theme-mode`，兼容读取旧 `sd-theme-v2`）；
  - 通过 `window.matchMedia("(prefers-color-scheme: dark)")` 监听系统主题变更事件（`change`），计算实际生效的 `resolvedTheme: "light" | "dark"`，写入 `document.documentElement.dataset.theme = resolvedTheme` 并传给 `<Chart theme={resolvedTheme} />`；
  - 在顶栏右侧 `.topbar-right`（「更多」左侧）放置精致紧凑的三态切换分段控件或带即时切换胶囊（`Sun` 浅色 / `Moon` 深色 / `Monitor` 跟随系统，`height: 32px`，符合 `emil-design-eng` 轻快过渡与 `a11y` `aria-pressed` / `radiogroup` 规范）。

### 5. 顶栏美债收益率胶囊与二级解读面板新增 COMEX 黄金信息
- **本机网络实测已验证可用的免 Key 公开双源方案**（2026-11-24 实测通过）：
  1. **主源（全球通用 JSON）**：Yahoo Finance COMEX 期金主力 `https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?range=2mo&interval=1d`（及 `query2` 镜像，`User-Agent: Mozilla/5.0`，实测 HTTP `200`，`exchangeName: "CMX"`, `fullExchangeName: "COMEX"`, `currency: "USD"`，单次返回实时价 `regularMarketPrice`、昨收、日内高低与近 2 个月日线以计算 21 日变动 `%`）；
  2. **热备源（中国大陆直连 183ms）**：东方财富 COMEX 黄金主力日线 `https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=101.GC00Y&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56&klt=101&fqt=0&lmt=30&end=20500101`（实测 HTTP `200`，返回 `GC00Y COMEX黄金` 最新价、昨收与 21 日序列）；
  3. *注：Stooq 存在浏览器 JS 验证拦截，按工程准则不予采用。*
- **前后端改动点**：
  - 后端 [`research.py`](../signaldesk/research.py) + [`demo.py`](../signaldesk/demo.py) + [`service.py`](../signaldesk/service.py) + [`security.py`](../signaldesk/security.py)：新增 `fetch_comex_gold()` 与 `gold_context()`，在 `refresh_macro()` 中每 5 分钟异步更新并缓存至 `store`（`comex_gold:live`），在 `snapshot()` 顶层输出 `gold` 字段并纳入 `safe_snapshot()` 公开市场研究上下文；
  - 前端 [`GuidePopover.tsx`](../frontend/src/GuidePopover.tsx) + [`types.ts`](../frontend/src/types.ts)：顶栏胶囊精巧并列展示 `美债10Y X.XX% · COMEX金 $X,XXX (+X.X%)`（`<=1360px` 窄屏自动隐藏涨跌幅后缀防拥挤），点击展开的二级弹层升级为「美债收益率与 COMEX 黄金看板」，新增 **COMEX 黄金价格/21日变动及与 10Y TIPS 实际利率联动解读卡**。

---

## 五、后续宏大演进路线

完成上述 5 项交互精修后，按 [`TODO.md`](../TODO.md) 规划推进多工作台独立分页架构：
1. **P0 `bt-1.0.0`**：顶栏新增 `[ 看盘与指标 | 策略与回测 ]` 独立页面切换，落地 6 套「波浪 + 点位 + 技术指标 + 宏观避险」零未来函数实战回测与单股 K 线 B/S/X 复盘；
2. **`macro-1.5`**：将历史四象限条件收益分布融入宏观全景面板；
3. **P1 `screen-1.0.0`**：上线第三个独立页面「选股发现」工作台，打通 `选股 → 回测检验 → 收藏看盘` 闭环。
