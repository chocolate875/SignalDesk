# V0.1.0 验收记录

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
