# AGENTS.md — SignalDesk 协作与工程规范

本文件为所有在此仓库工作的 AI Agent 与开发者提供架构约定、红线约束、视觉规范以及文档/Git 连续性要求。

## 1. 项目定位与技术栈

- **定位**：本机美股长期持仓复核与桌面看盘工具。先看美债利率与个股估值，再用已确认日线、个人计划价和手动触发的 Codex 总结辅助复核。
- **后端**：Python 3.12+（`uv` 管理），FastAPI + Uvicorn + WebSocket + SQLite（WAL）+ `longbridge`（仅只读行情/持仓/自选接口）+ `pandas` / `ta` + `exchange-calendars` + `httpx`。入口为 `signaldesk/desktop.py` 与 `signaldesk/app.py`。
- **前端**：React 19 + TypeScript + Vite 6 + ECharts 6 + Lucide Icons，位于 `frontend/`。生产构建输出到 `frontend/dist/`，由 Python FastAPI 直接提供静态资源，不依赖外部 CDN。

## 2. 核心工程与安全红线

1. **严格只读，绝不下单**：`LongPortFeed`（`signaldesk/providers.py`）只包装只读接口（持仓、资金、自选分组、日线、估值、报价、日历），严禁增加下单、撤单、融资融券、期权或修改券商自选的方法。
2. **隐私与凭据隔离**：
   - 凭据与运行状态保存在本机 `%LOCALAPPDATA%\SignalDesk`（或 `SIGNALDESK_DATA_DIR`），Windows 使用 DPAPI 加密，Linux 须配置 `SIGNALDESK_VAULT_KEY`。
   - 发送给 Codex 的脱敏快照必须严格通过 `signaldesk/security.py` 的 `safe_snapshot()` 白名单生成，**严禁泄露账户 ID、持仓股数、可用数量、成本价、净资产或成交流水**。
   - Codex 子进程必须通过 `safe_child_environment()` 隔离环境变量，保持 `--ignore-user-config --ephemeral` 与精确只读目录权限。
   - QQ 通知必须通过 `signaldesk/notifications.py` 的 `qq_text()` 白名单，不泄露仓位与金额。
3. **因果与数据诚实**：
   - 技术指标仅使用已确认且 `bar_end <= now` 的 K 线；缺交易日、无效 OHLCV 或未就绪窗口必须截断预热并显示不可用，禁止未来数据泄露、前向填充或补零。
   - 禁止编造行情、财报、估值、利率或测试结果；未实测项必须如实写明未验证。
4. **Codex 纯手动触发**：
   - `CodexSettings.automatic` 默认为 `False`，`Monitor.on_events()` 不得自动入队 Codex 任务，仅在用户手动触发分析接口时执行。
5. **模型兼容性**：`signaldesk/models.py` 使用 `StrictModel(extra="forbid")`，为既有模型新增字段时必须提供向后兼容默认值，避免破坏用户本地既有 SQLite 序列化数据。

## 3. UI 视觉规范（企业简洁风）

修改前端页面或样式（`frontend/src/`）时必须遵循以下规则：

- **默认主题与配色**：默认启用亮色「企业简洁风」（保留深色切换）。画布底色 `#f8fafc`（Slate Mist），卡片与面板 `#ffffff` 配 `1px solid #e5e7eb` 描边与 `12px` 圆角；全站只使用一种主蓝 `#1e40af`（Corporate Blue），`#3b82f6`（Action Blue）仅用于焦点环与选中高亮，不使用渐变按钮或重阴影。
- **字号与排版**：全站采用 `Inter` + 系统无衬线中文字体栈；**全局严禁出现小于 `12px` 的字号**；正文/按钮 `14px–16px`、行高 `1.6–1.65`、长段落控宽 `<= 70ch`；所有价格、涨跌幅、估值、评分、时钟必须使用 `font-variant-numeric: tabular-nums`。
- **交互与无障碍**：按钮圆角 `8px`、状态徽章圆角 `999px` 且必须带状态圆点或图标；hover 上浮不超过 `2px`，active 缩放 `0.98`，所有动效 `<= 200ms ease-out`；所有交互控件必须保留 `2px` offset 焦点环，并支持 `prefers-reduced-motion`。

## 4. 文档与 Git 连续性纪律（每次改动必做）

为保证多轮迭代的上下文连续性与可追溯性，**每次完成功能、UI、口径或架构修改后，必须在交付前完成以下步骤**：

1. **同步更新文档**：
   - [README.md](README.md)：同步使用说明、功能入口、配置项与开发命令。
   - [TODO.md](TODO.md)：勾选已完成事项、更新当前进度与待验证项，维护后续迭代路线图（如选股推荐功能规划）。
   - [docs/signals.md](docs/signals.md)：若指标、评分、verdict 规则、估值/宏观口径或模型边界发生变化，必须同步更新公式与说明。
   - [docs/verification.md](docs/verification.md)：按日期记录本轮实际跑过的测试、构建、浏览器/实盘验收结果，以及尚未验证的部分。
2. **规范检查并提交 Git**：
   - 提交前执行 `git status -s` 与 `git diff --stat`，确认**没有任何运行时/私密/构建产物**（如 `.runtime/`、`data/`、`*.sqlite*`、`*.encrypted`、`frontend/dist/`、`output/`、`.playwright-cli/`）进入 Git 跟踪区。
   - 运行 `pytest tests/test_integrations.py -k test_no_private_runtime_files_tracked -q` 确保隔离测试通过。
   - 在本地分支按职责拆分为清晰的 Conventional Commits（例如 `feat: ...`、`fix: ...`、`docs: ...`），提交说明准确反映实际改动。
   - **除非用户明确要求，不要配置 Git 远程仓库，也不要执行 `git push`。**

## 5. 常用命令

```powershell
# Python 单元测试与代码检查
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check signaldesk tests

# 前端类型检查与生产构建（Windows 沙箱若遇 Vite realpath EPERM 需在沙箱外执行）
Set-Location frontend
npm run build

# 启动本机无界面服务（Windows 双击可用 Start-SignalDesk.cmd）
.venv\Scripts\python.exe -m signaldesk.desktop --headless --port 8765
```
