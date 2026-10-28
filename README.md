# SignalDesk

本机优先的美股技术信号工作台：**融合指标看板 + 长短线独立提醒 + Codex 分析 + QQ 官方通知**。

默认打开完全合成的演示行情与示例持仓。没有自动下单、做空或期权执行接口。技术评分描述结构，不代表上涨概率。

## 立即使用

在Windows双击 [Start-SignalDesk.cmd](Start-SignalDesk.cmd)，打开 `http://127.0.0.1:8765`，同时显示系统托盘图标。

- 首次运行在设置中主动展示“登录后自动启动”；默认关闭，可随时修改。
- 关闭浏览器继续后台监控；托盘菜单“退出并停止监控”才会停止程序。
- 演示模式不会自动向QQ或Codex发送事件。可以手动使用合成快照测试Codex分析。
- 监控依赖电脑开机联网；关机、睡眠及断网期间无法实时提醒，恢复后补数据并保留缺口状态。

如需从Git新检出后安装：Python 3.12+、uv、Node.js 20.19+/22+。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
.\Start-SignalDesk.cmd
```

前端编译后由本机Python服务提供，日常运行无需Node服务；所有字体、图表和页面资源本机加载。

## 接入顺序

### 1. LongPort行情与持仓

在“规则与接入 → LongPort数据”填写官方OpenAPI的App Key、App Secret及Access Token；保存后在“运行方式”切换为实盘。凭据只在本机填写，不要发到聊天。

程序使用官方SDK的只读持仓、资金、交易日历、行情及K线接口。启用夜盘，分别处理夜盘/盘前/常规/盘后。OpenAPI行情权限与App独立；没有数据或权限时显示受限，不代表市场没有异动。

实盘持仓初始为未分类，点击股票行右侧编辑按钮分配长期与短线数量。同股可分仓，合计超过实际数量会被拒绝；外部交易产生数量差异时提示核对。观察股票数量保持0，可独立选择长期/短线策略。

### 2. Codex

确保本机Codex CLI已经登录。程序读取现有模型与推理强度偏好，采用专用配置运行非交互任务，不修改全局Codex设置，也不另行切换为API计费模式。

- 个股“发送预览”可以查看实际脱敏快照，再手动分析。
- 实盘关键融合事件和重要关键价自动分析；默认单并发、同股30分钟冷却、北京时间每日24次自动调用上限。
- 默认单次等待600秒，适配现有较高推理强度；可在设置中调整，等待期间不阻塞监控。
- 发送股票、技术指标、长短线分类、仓位/盈亏百分比等已授权脱敏信息；不发送账户标识、股数、实际金额、成本和流水。
- 使用精确文件读取范围、关闭继承插件/工具/记忆/钩子，并通过标准输入发送快照。自动分析依赖本机快照；已有Longbridge插件仍可在你交互式使用Codex时补充核查。
- 结果保存为结构化判断、证据、风险和等待条件。超时、登录失效、额度不足及沙箱未就绪会明确显示，不降低隔离要求、不影响行情监控。

Codex客户端在本机执行，**分析内容仍会发送到模型服务**。本项目不把云端分析称为本地推理。

### 3. QQ官方机器人

在“QQ官方机器人”设置中填写AppID、AppSecret、接收类型及与该AppID绑定的 `user_openid` 或 `group_openid`，保存后主动点击测试。

OpenID不是普通QQ号/群号。可从你已有官方机器人的事件或平台调试记录取得；首版是仅出站发送适配器，不部署公网事件回调、也不托管QQ账号。若尚无目标OpenID或主动/订阅权限，需先在QQ官方平台完成配置。

成功、待授权、限流、失败、结果未知分别显示，HTTP 200中的业务失败不会被当作成功。普通QQ事件30秒合并，关键风险优先；超时结果不明确时不盲目重发。目标修改后旧队列不会转发到新目标。

QQ默认只发送股票、技术事件、结构分、简短说明与时间，不发送仓位和金额。微信后续可以实现同一个 `NotificationChannel` 接口，现有引擎与去重机制无需改写。

## 数据与隐私

- 默认运行目录：Windows `%LOCALAPPDATA%\SignalDesk`；Linux `~/.local/share/signaldesk`。可用 `SIGNALDESK_DATA_DIR` 指定其他本机目录。
- SQLite存储行情、分类、规则、事件、投递和分析状态；敏感文件与Codex快照均不纳入Git。
- Windows凭据使用当前用户DPAPI加密，前端无法回读。Linux实盘需要提供Fernet格式的 `SIGNALDESK_VAULT_KEY`，未配置时不会明文保存凭据；演示和无界面运行不需要该密钥。
- 服务仅监听127.0.0.1，校验Host/Origin和本机会话，不开放局域网，不加载外部CDN、没有云端遥测，也未配置Git远程仓库。

## 开发、测试和回放

```powershell
uv sync --frozen
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\ruff.exe check signaldesk tests
cd frontend
npm ci
npm run build
```

无界面服务：

```powershell
.venv\Scripts\python.exe -m signaldesk.desktop --headless --port 8765
```

Linux复用Python核心，先构建/复制前端资源，再运行 `python -m signaldesk.desktop --headless`。ARM64依赖可用性与实际模型调用、长桥连接性能仍须在目标开发板验证。

回放及精确公式见 [算子与评分说明](docs/signals.md)。项目选型、许可证和来源见 [量化项目调研](docs/research.md)。验收记录见 [验收说明](docs/verification.md)。Python与前端分别由 `uv.lock`、`frontend/package-lock.json` 锁定版本。
