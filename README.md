# SignalDesk

首个正式大版本为 **v1.0.0**，包含美股、港股和沪深 A 股看板、本地缓存及局域网只读访问。

> [!IMPORTANT]
> SignalDesk 是一个完全使用 AI Agent 开发的个人项目。**本项目仅供学习与研究，不提供任何投资意见。** 界面中的评级、参考价位和风险预算均为模型输出。

本地优先（Local-First）的美股、港股与沪深 A 股长期持仓与自选股桌面复核工作台。默认采用克制清晰的「企业简洁风」16:9 三栏布局（支持深浅色与红绿涨跌切换），集成宏观流动性与美国国债曲线、个股估值 / ETF 专属特征、前复权日线与实时试算、严格因果学术因子（`fusion-2.0.0`）、动态风险预算以及手动触发的**本地官方多 Agent 长期复核（Google Antigravity CLI 官方 ACP / OpenAI Codex CLI 官方 exec）**。

默认启动完全合成的演示行情与示例持仓，开箱即用。系统**严格只读**，不含任何自动下单、撤单、做空或期权交易执行接口。评分、点位与风险预算用于描述价格结构与历史波动特征。

---

## 核心特性

- **16:9 精简三栏看盘与右侧模块化定制**：
  - **紧凑顶栏**：浓缩运行状态、「大势 · 四象限 / 红灯数」全景入口、`美债10Y · COMEX金` 速览胶囊（点击展开 `3M/2Y/10Y`、NY Fed 12M 衰退概率、`10Y TIPS` 实际利率与 COMEX 黄金联动解读）、外置三态外观切换（浅色 / 深色 / 跟随系统）以及清爽无重复的「更多」二级辅助菜单。
  - **左栏自选与收藏**：支持长桥多市场持仓与自选分组只读同步、本机 `★ 收藏`、4 维清晰排序（`买卖评级` / `风险预警` / `今日涨幅` / `今日跌幅`）与行动标签图例。市场筛选可与收藏、持仓、自选分组及搜索叠加。代码、状态或证券类型、价格同排对齐，次行显示市场、名称、涨跌幅及评级。手动添加可输入 `AAPL`、`00700.HK`、`600519.SH`、`000001.SZ`，短码 `700.HK` 会归一为五位编号。港股与沪深标的优先显示券商中文名称。
  - **中栏 K 线与双口径联动**：前复权日线（`ForwardAdjust` 自动平滑拆股/合股跳空并具备除权漂移自愈）默认展示「近6月」（`126` 根）且默认关闭 `MACD` 副图、切换不同标的严格保持当前缩放比例与日期区间；支持动态可见窗口紧密 Y 轴缩放、右侧 126 日筹码分布直方图（`POC / 70% 价值区`）、主要突破/防守共振主线、买卖区半透明色带与中级波浪趋势通道；支持一键切换 **「收盘确认（正式基准） ↔ 最新行情试算（盘中/盘外实时重算预览，零数据库污染）」**。
  - **右栏可自定义研判面板**：7 大独立研判模块（`买卖点位评级（含突破/防守与筹码分布）`、`波浪与趋势分析`、`盘外动态`、`长期计划价位`、`结构评分与学术因子`、`估值与资产特征`、`独立风险检查`）支持自由拖拽排序与显隐开关。
- **`fusion-2.0.0` 降噪规则与严格因果学术因子（`factors.py`）**：
  - 经本地多股横截面因果回放验证，剔除短周期高共线冗余指标，采用 `45% 连续趋势 + 40% 多周期动量 + 15% 10日平滑资金顺向度`；
  - 零付费数据源计算 6 组核心学术因子：**残差动量信息比**（vs `SPY` 扣 Beta 不扣自身 Alpha）、**FIP 信息离散度**（区分连续慢牛 vs 单日脉冲）、**52 周高点锚定比**、**Yang-Zhang 无偏波动率**（计入隔夜跳空）、**下行 Beta** 与 **近月 `MAX5` 彩票过热护栏**，辅以 60 日已实现偏度、`Amihud` 流动性冲击与换手率/总市值。
- **宏观水位（`macro-1.0.0`）、盘外动态（`ext-1.0.0`）与动态风险预算**：
  - 免 Key 拉取 14 条公开 FRED 宏观序列（按官方发布时间严格对齐）与 6 只全市场基准 ETF，合成六分项指示灯与四象限底色；
  - 融合夜盘 / 盘前 / 盘后独立行情、`$100万` 流动性门控及**近 20 日隔夜 vs 日内拉锯诊断**（对历史「高开低走」标的在盘外急涨时主动提示防追高）；
  - 基于目标波动率与宏观红灯水位给出纯参考性的**建议敞口系数（`suggested_exposure_ratio`）**与**近 60 日峰值 `2.5×ATR14` 移动保护位（`trailing_stop`）**。
- **个股与 ETF / 指数基金智能分流（`instruments.py`）**：
  - 自动识别宽基、行业、商品及杠杆/反向 ETF，停用易失真的基金主体 PE/PB，改用近 1 年高点回撤、价格分位、Yang-Zhang 波动率与美债变动评估，并对反向/高倍杠杆 ETF 施加专属复利损耗风控护栏。
- **多 Agent 官方本地协议长期复核（`agent_bridge.py` / `codex_bridge.py`）**：
  - **仅支持官方原生协议，拒绝一切非官方第三方包装器**，且强制纯手动触发、零副作用只读隔离运行：
    - **Google Antigravity CLI**：通过官方 [Agent 客户端协议 (ACP)](https://antigravity.google/docs/cli/acp/)（`agy acp`，JSON-RPC 2.0 over `stdio`）通信，握手关闭文件读写与终端能力并自动拒绝一切工具权限请求；
    - **OpenAI Codex CLI**：通过官方 `codex exec --output-schema` 最小目录只读权限运行；
  - 发送前可通过「查看脱敏预览」逐字核对白名单 JSON（绝不含账户标识、持仓股数、成本价、金额或流水）。

---

## 仓库目录结构

```text
SignalDesk/
├── signaldesk/              # Python 后端核心包（FastAPI + 因果量化引擎 + 多 Agent 桥接）
│   ├── desktop.py           # 桌面托盘与无界面服务入口（CLI: signaldesk）
│   ├── launcher.py          # Windows 单实例启停与健康探测守护器
│   ├── app.py               # FastAPI 路由、WebSocket 推送与本地会话安全校验
│   ├── service.py           # 核心监控服务 Monitor、缓存协同与实时试算引擎
│   ├── models.py            # StrictModel 数据契约与配置模型
│   ├── security.py          # DPAPI/Fernet 加密凭据库与 safe_snapshot 脱敏白名单
│   ├── storage.py           # SQLite WAL 持久化存储
│   ├── providers.py         # LongPort 只读行情/持仓/自选接口与双网关测速回退
│   ├── indicators.py        # fusion-2.0.0 技术指标与三维平滑结构评分
│   ├── factors.py           # 严格因果学术因子引擎（残差动量 / FIP / Yang-Zhang / MAX5 等）
│   ├── factor_eval.py       # 多股横截面因果回放评测工具（CLI: signaldesk-eval）
│   ├── forecast.py          # 去重锚点买卖区间、正交四维 5 级评级与 risk_budget
│   ├── wave_trend.py        # 因果 ZigZag 拐点、平行趋势通道与波浪校验
│   ├── instruments.py       # 个股 vs ETF/杠杆基金分类与基金特征计算
│   ├── extended_hours.py    # ext-1.0.0 夜盘/盘前/盘后独立行情与日夜拉锯预警
│   ├── macro.py             # macro-1.0.0 FRED 宏观流动性六分项与四象限引擎
│   ├── research.py          # 美国财政部国债收益率曲线与名义/实际股债利差
│   ├── agent_bridge.py      # OfficialAgentBridge 协议、Antigravity ACP 客户端与 AgentHub
│   ├── codex_bridge.py      # OpenAI Codex CLI 官方 codex exec 桥接器
│   ├── events.py            # 事件状态机与冷却去重
│   ├── notifications.py     # 桌面通知与 QQ 官方机器人出站通知通道
│   └── replay.py            # 历史 CSV/JSON 离线回放工具（CLI: signaldesk-replay）
├── frontend/                # React 19 + TypeScript + Vite 6 + ECharts 6 前端工程
│   ├── public/              # 多尺寸品牌图标（favicon.svg / .ico / apple-touch-icon.png）
│   ├── src/                 # 前端组件、模块化右栏配置与企业简洁风样式
│   └── package.json         # 前端依赖声明（由 package-lock.json 锁定）
├── tests/                   # 111 项后端因果性、筹码分布、安全隔离、API 与多 Agent 协议单元测试
├── scripts/
│   └── setup.ps1            # 一键初始化 uv 锁定环境并构建前端静态资源
├── docs/
│   ├── signals.md           # 算子、fusion-2.0.0 公式、学术因子、宏观与多 Agent 口径字典
│   ├── research.md          # 量化文献调研与本机 75 股 / 9,307 截面因果回放实证报告
│   ├── research_todo.md     # 学术精简与高有效指标分阶段实施清单（已全部完成）
│   └── verification.md      # 历次自动化测试与双分辨率实盘验收记录
├── AGENTS.md                # 协作者与 AI 智能体架构交接规范及工程红线
├── TODO.md                  # 里程碑归档与下一阶段路线图（选股推荐工作台等）
├── .python-version          # Python 解释器版本锁定（3.12）
├── pyproject.toml           # Python 项目元数据、依赖与命令入口定义
├── uv.lock                  # uv 精确跨平台依赖锁文件
├── Start-SignalDesk.cmd     # Windows 一键启动脚本
├── Stop-SignalDesk.cmd      # Windows 一键停止脚本
└── Clean-SignalDesk.cmd     # Windows 本地数据清理脚本
```

---

## 环境管理与快速开始（基于 `uv`）

本项目采用 **[uv](https://docs.astral.sh/uv/)** 管理 Python `3.12+` 虚拟环境与精确依赖锁（`uv.lock`），前端由 Node.js `20.19+ / 22+`（`npm ci`）构建静态产物，日常运行仅需本机 Python 进程。

### Windows 一键启动

1. 从仓库克隆或进入 `SignalDesk` 目录后，直接双击 [Start-SignalDesk.cmd](Start-SignalDesk.cmd)（首次运行会自动调用 [scripts/setup.ps1](scripts/setup.ps1) 执行 `uv sync --frozen` 与前端构建，就绪后自动打开 `http://127.0.0.1:8765`）。
2. 需要退出托盘并停止后台监控时，双击 [Stop-SignalDesk.cmd](Stop-SignalDesk.cmd)。
3. 如需手动执行完整初始化：
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
   .\Start-SignalDesk.cmd
   ```

---

## 外部通道接入说明（全部可选）

### 1. 长桥（LongPort / Longbridge）只读行情与自选
- 在看板「设置 → 长桥数据」选择默认的 **OAuth 2.0**，点击「登录长桥」并在浏览器完成只读授权（`account.read` 与 `watchlist`）。SignalDesk 自动注册客户端，将令牌加密保存在本机并按需续期。也可在同一设置页手动录入 API Key。
- 连接时自动测速优选 `.cn` / `.com` 网关，支持断线自动回退、盘前/盘后/夜盘实时报价及前复权日线自动对齐。
- 启动时批量获取报价，随后优先接收实时推送。缺价、推送停更或队列溢出时，按受影响标的合批补查。账户在活跃交易时段每 5 分钟同步，各市场均休市时每 30 分钟同步。长桥自选每 15 分钟同步，也可在设置中立即同步。左栏显示简短的同步时间，悬停可查看完整时间。
- 日线优先读取本地 SQLite 缓存，收盘后按缺口限速补齐。证券资料和估值各有缓存与刷新周期，详见[长桥数据刷新口径](docs/signals.md#长桥数据刷新)。

### 2. 本地官方 Agent 长期复核（Antigravity CLI / Codex CLI）
在看板「设置 → Agent 复核」或右侧「AI 复核」面板可随时切换默认首选引擎：
- **Google Antigravity CLI（官方 ACP 协议）**：按官方文档安装 `agy` 后，在本机终端运行一次 `agy acp --login` 完成登录（或配置 `GEMINI_API_KEY`），SignalDesk 即通过官方 `agy acp` 标准协议调用。
- **OpenAI Codex CLI（官方非交互模式）**：安装 Codex CLI 后运行 `codex login` 登录，SignalDesk 通过 `codex exec --output-schema` 隔离只读调用。
- 若已为 Agent CLI 配置 API Key，SignalDesk 可从启动进程的环境向子进程传递 `GEMINI_API_KEY` 或 `OPENAI_API_KEY`。
- 本地 CLI 执行时，脱敏分析文本会发送至对应模型服务商（Google / OpenAI）完成推理；本工具所有复核均为用户手动点击触发，后台绝不自动消耗额度。

### 3. QQ 官方机器人通知
- 在「设置 → QQ官方机器人」填入官方平台 AppID、AppSecret 与绑定的 `user_openid` / `group_openid` 即可测试发送；通知内容经严格脱敏，不含持仓数量与金额。

---

## 开发、测试与因果评测命令

```powershell
# 同步锁定环境（含 pytest / ruff 开发工具组）
uv sync --frozen

# 构建前端静态资源，供 API 图标路由测试和本机服务使用
npm --prefix frontend ci
npm --prefix frontend run build

# 运行代码静态检查与全量单元测试
uv run ruff check signaldesk tests
uv run pytest -q

# 启动无界面本机开发/实盘服务
uv run signaldesk --headless --port 8765

# 运行离线多股因果因子回放评测或单标的回放
uv run signaldesk-eval --output .runtime\factor_eval.json
uv run signaldesk-replay --output .runtime\replay-demo.json
```

---

## 清理本地数据

在 Windows 双击 [Clean-SignalDesk.cmd](Clean-SignalDesk.cmd)，也可在终端指定 `Clean-SignalDesk.cmd cache` 或 `Clean-SignalDesk.cmd all`。脚本显示当前数据目录，包含 `SIGNALDESK_DATA_DIR` 覆盖设置。

- **只清 K 线缓存**（`cache`）删除所有市场的日线、分时与宏观基准 K 线。设置、持仓分类、自选和凭据保留。下次实盘同步会重新拉取行情。
- **重置全部本地数据**（`all`）删除 SignalDesk 数据库、长桥及 QQ 凭据和 AI 复核导出。下次启动会进入默认演示模式，再使用实盘时需重新接入。

输入 `CLEAN` 后，脚本会停止该数据目录中运行的 SignalDesk 再清理。完成后可重新运行启动脚本。其他平台可用 `uv run python -m signaldesk.cleanup` 打开同一个菜单。

## 局域网只读看板

如主机正在运行 SignalDesk，先用 `Stop-SignalDesk.cmd` 退出，再用 `Start-SignalDesk.cmd --lan` 启动。无托盘模式可运行 `uv run signaldesk --headless --lan --port 8765`。在主机的本机看板打开「设置 → 运行与通知 → 局域网只读访问已启用」查看访问码。在同一局域网的设备上打开 `http://主机内网IPv4:8765` 并输入访问码。

局域网页面可查看行情、图表和技术结构。券商权限、计划编辑、提醒和 AI 复核继续从主机操作。访问码在服务重启后更新。服务使用 HTTP，适合可信私有网络。

## 数据安全与文档索引

- **本机数据目录**默认为 Windows 的 `%LOCALAPPDATA%\SignalDesk` 或 Linux 的 `$XDG_DATA_HOME/signaldesk`（未设置时为 `~/.local/share/signaldesk`）。需要更换目录时，在启动进程的环境中设置 `SIGNALDESK_DATA_DIR`。
- **凭据加密**在 Windows 上由当前用户的 DPAPI 完成。Linux 用户如需保存或读取长桥、QQ 凭据，须在启动进程的环境中设置 `SIGNALDESK_VAULT_KEY`，并在后续启动时使用同一把 Fernet 密钥。服务默认绑定 `127.0.0.1` 并校验同源会话令牌。
- **延伸文档**：
  - 工程交接、Git 同步清单与待续任务说明：[docs/handover.md](docs/handover.md)
  - 个人 rebase、协作 merge、主分支保护与 GitHub 检查：[CONTRIBUTING.md](CONTRIBUTING.md)
  - 工程规范与模块交接字典：[AGENTS.md](AGENTS.md)
  - 算子、公式与风控口径：[docs/signals.md](docs/signals.md)
  - 学术文献与因果回放实证：[docs/research.md](docs/research.md)
  - 测试与实盘验收记录：[docs/verification.md](docs/verification.md)
  - 迭代归档与多工作台路线图：[TODO.md](TODO.md)
