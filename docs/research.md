# 量化项目调研与首版取舍

核验日期：2026-10-28。用途：个人美股多头持仓技术监控；不训练预测模型、不执行交易。以下是公开资料调研，未读取任何真实账户。

| 项目 | 核验来源与许可证 | 可借鉴能力 | V1 取舍及平台考虑 |
|---|---|---|---|
| Microsoft Qlib | [仓库](https://github.com/microsoft/qlib)、[表达式算子](https://github.com/microsoft/qlib/blob/main/qlib/data/ops.py)、[Alpha158](https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py)，MIT | 延迟、滚动窗口、尺度归一化、因子与数据处理解耦 | 参考设计，自行实现有限白名单算子；不引入完整训练、Cython及模型存档链路。避免将未来标签用作实时特征。 |
| vectorbt | [仓库](https://github.com/polakowo/vectorbt)、[许可证](https://github.com/polakowo/vectorbt/blob/master/LICENSE.md)，Apache-2.0 **附 Commons Clause** | 向量化研究、参数比较与回放 | 参考研究方法；不作为运行依赖、不复制源码。Commons Clause 不是无附加条件的 Apache 许可；避免增加 Numba/LLVM 对开发板的部署负担。 |
| vn.py / VeighNa | [仓库](https://github.com/vnpy/vnpy)、[许可证](https://github.com/vnpy/vnpy/blob/master/LICENSE)，MIT | 事件引擎、网关解耦、指标缓冲、Alpha158特征工程 | 借鉴数据/信号/通知分层；不引入完整桌面交易终端和订单网关。 |
| LEAN | [仓库](https://github.com/QuantConnect/Lean)、[许可证](https://github.com/QuantConnect/Lean/blob/master/LICENSE)，Apache-2.0 | 事件驱动、历史与实时处理一致、可插拔模型 | 参考时点一致的回放与实时共用计算路径；不引入.NET交易引擎。仓库有ARM构建文件，但这不等于本项目已完成开发板实测。 |
| ta | [仓库](https://github.com/bukosabino/ta)、[API](https://technical-analysis-library-in-python.readthedocs.io/en/latest/ta.html)，MIT | SMA/EMA、RSI、MACD、布林带、ATR | **直接依赖**。保留 fillna=False，并在引擎中额外验证预热和有效数据；ATR库的前置零值不视作有效信号。采用版本记录在 uv.lock。 |
| LongPort | [SDK](https://pypi.org/project/longport/)、[夜盘与权限](https://open.longportapp.com/docs/qa/broker)，MIT/Apache-2.0 | 只读账户、历史K线、实时推送、交易日与时段 | **直接依赖**。App与OpenAPI权限独立；客户端必须主动启用夜盘。无实时权限时明确标记，不能把缺行情当无异动。 |

## 采用方案

### 维护状态与平台核验

以下由官方 GitHub API 的仓库元数据和 latest release 在核验日读取；`pushed_at`表示仓库最近推送，不能独自证明代码质量。未采用框架的版本仅作为调研快照，不进入运行锁文件。

| 项目 | 调研版本 / 最近仓库推送（UTC） | Windows / Linux 与回放口径 |
|---|---|---|
| Qlib | [v0.9.8](https://github.com/microsoft/qlib/releases/tag/v0.9.8)，2026-10-22 | 官方提供两平台安装说明；完整数据集、训练与回测链路较重。借鉴表达式与Alpha158，V1用已完成K线自行回放。 |
| vectorbt | [v1.2.0](https://github.com/polakowo/vectorbt/releases/tag/v1.2.0)，2026-10-23 | Python/NumPy/Numba栈可覆盖两平台，依赖二进制轮子；向量化回测便于比较参数，V1不引入其交易组合模拟。 |
| vn.py | [4.5.0](https://github.com/vnpy/vnpy/releases/tag/4.5.0)，2026-10-27 | Windows/Linux安装路径齐全，GUI和交易网关增大部署面；借鉴事件引擎、历史/实时解耦，不启用订单链路。 |
| LEAN | 主分支参考，2026-10-27 | C#/.NET和Docker跨平台，历史/实盘事件机制完整；GitHub latest release仍显示2017年的v2.4.0.1，**不把旧release时间误判为停止维护**。V1只参考架构。 |
| ta | 直接采用0.11.0，2026-03-18 | 纯Python/pandas栈适用于两平台；提供指标、不提供提醒/账户/完整回放。维护节奏比上述框架低，V1用独立数值及边界测试约束依赖行为。 |

上述五个仓库核验时均未归档。元数据来源为各官方仓库的 `https://api.github.com/repos/{owner}/{repo}` 与 `/releases/latest`；ta未发布GitHub latest release，采用安装锁定版本。Windows安装及实际测试结果见验收文档；Linux为代码兼容设计，未宣称目标硬件实测。

以 pandas/numpy + ta 建立轻量计算核心，SQLite持久化状态和通知队列，LongPort独立数据适配器，React/ECharts本机静态看板。运行依赖的精确版本由 `uv.lock`、`frontend/package-lock.json` 锁定。上述未采用框架按核验日公开主分支作设计参照，**没有复制上游实现**；不声称固定了它们的发行版本或实盘收益。

算子 -> 因子 -> 三维评分 -> 独立风险门控 -> 事件 -> 通知/Codex，所有层携带数据时间与规则版本。回放只处理当时已经结束的K线。当前持仓的模拟历史不能充当真实账户业绩。

## QQ 与 Codex

- [QQ Access Token](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/access-token.html)：服务端保存 AppSecret、按 expires_in 刷新。错误可能在HTTP 200响应体内。
- [QQ API指南](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/api-call-guide.html)：目标是与AppID绑定的OpenID，不是普通QQ号。主动消息权限/订阅授权/频控以平台结果为准；不伪造msg_id绕过限制。
- [Codex非交互模式](https://developers.openai.com/codex/noninteractive/)：使用本机CLI及现有登录，结构化输入输出。输入会发送至模型服务，不能称为纯本地推理。
- [Codex权限](https://learn.chatgpt.com/docs/permissions)：普通read-only允许广泛读取；自动分析使用精确只读根目录和独立配置，隔离原始账户数据库及凭据。

## 维护与兼容性评估方法

核验了官方仓库、源码/文档与许可证；不以星数或未运行的演示推断安全性。直接依赖在本机安装后记录精确版本并执行测试。Windows是V1实测目标，Linux保留无界面核心、平台条件依赖与凭据适配；ARM64性能和券商连接仍需目标硬件验收。
