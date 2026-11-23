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

## 宏观水位、流动性与「市场大势」调研（2026-11-23）

用途：评估是否在个股复核之外增加**市场整体层面**的宏观水位、流动性与大势视图。本节仅为文献与数据口径调研和方案设计，**尚未实现代码，也未实测任何外部数据接口**；文中阈值均为设计草案，未经回测。

### 结论与定位

1. **定位为「风险环境底色」，不做择时信号。** 证据最扎实的是金融条件与信用利差对**下行尾部风险**的预测（Adrian 等 2019；Gilchrist & Zakrajšek 2012），而不是对指数下月涨跌的预测。
2. **可预测性警示。** Welch & Goyal（2008）及 Goyal, Welch & Zafirov（2024）显示大多数宏观预测变量样本外跑不赢历史均值，2008 年后新提出的变量超过三分之一在延长样本内即不再显著。因此不输出黑箱「大势总分」，不做点位预测。
3. **「美联储净流动性 = WALCL − TGA − RRP」属于从业者经验口径**，不是经同行评审的定价因子：准备金只能由银行持有，RRP 下降常是资金转向国库券的构成变化。若展示必须标注「经验口径」，且不能单独驱动结论。
4. **技术与宏观互补。** Neely, Rapach, Tu & Zhou（2014）发现技术指标擅长识别见顶、宏观变量擅长识别见底，组合优于单独使用，与本项目「技术结构 + 估值利率」双支柱一致。

### 学术证据地图

| 主题 | 代表研究 | 核心结论 | 本项目启示 | 证据强度 |
|---|---|---|---|---|
| 金融条件 → 尾部风险 | Adrian, Boyarchenko & Giannone (2019, *AER*) | NFCI 收紧时未来增长分布左尾显著恶化，右尾基本不变 | 用 NFCI 刻画下行风险，不预测涨幅 | 强 |
| 信用利差 | Gilchrist & Zakrajšek (2012, *AER*) | 利差预测力几乎来自反映中介风险承受力的超额债券溢价 | 高收益 OAS / Baa 利差为核心分项 | 强 |
| 信用情绪反转 | López-Salido, Stein & Zakrajšek (2017, *QJE*) | 利差过低、信用过热约两年后反转并伴随经济走弱 | 利差处于历史低分位标黄（过热）而非标绿 | 中强 |
| 全球金融周期 | Miranda-Agrippino & Rey (2020, *REStud*) | 单一全球因子解释大部分风险资产共振，美国货币政策为主要驱动 | 联储政策、美元与风险偏好联动看 | 强 |
| 中介杠杆 | Adrian, Etula & Muir (2014, *JF*) | 券商杠杆冲击单因子解释约 77% 横截面收益 | 解释流动性重要性；季度数据不适合日常看板 | 强（横截面） |
| 流动性螺旋 | Brunnermeier & Pedersen (2009, *RFS*) | 保证金与亏损相互强化，流动性可突然枯竭 | 波动骤升与信用走阔同时出现时升级风险提示 | 强（理论） |
| 市场非流动性 | Amihud (2002, *JFM*) | 预期非流动性推高未来超额收益，意外上升使股价同步下跌 | 可用 ETF \|收益\|/成交额 构造指标 | 中 |
| 美元与全球杠杆 | Avdjiev, Du, Koch & Shin (2019, *AER: Insights*) | 美元走强、CIP 偏离扩大与跨境美元信贷收缩同时发生 | 美元快速走强作为全球流动性收紧旁证 | 中 |
| 准备金与回购 | Copeland, Duffie & Yang (NBER w28142) | 2019-09 回购飙升表明总准备金「充裕」不等于够用 | 准备金快速下滑、SOFR 高于 IORB 作为管道压力提示 | 中 |
| 收益率曲线 | Estrella & Mishkin (1998, *REStat*)；纽约联储 10Y−3M probit | 曲线斜率是 2–6 季度衰退最强单一预测变量；1998 年误报；倒挂解除常伴随降息与衰退初期 | 补充 10Y−3M，提示「倒挂解除≠风险解除」 | 强（衰退）/弱（择时） |
| 波动率风险溢价 | Bollerslev, Tauchen & Zhou (2009, *RFS*) | VRP 对 1–4 个月股市收益有预测力 | VIX² − HV20² 近似 VRP | 中强 |
| 波动管理 | Moreira & Muir (2017, *JF*) | 高波动期风险价格偏低，按波动反向调整敞口提升夏普 | 「波动环境」分项 | 中强（交易成本有争议） |
| 时间序列动量 | Moskowitz, Ooi & Pedersen (2012, *JFE*)；Faber (2007) | 过去 12 个月收益正向预测未来 1–12 个月；趋势过滤主要价值在截断深度回撤 | 指数相对 MA200 / 10 月均线、12-1 动量 | 强 |
| 市场广度 | Zaremba 等 (2021, *Economic Modelling*) | 64 国数据中广度高的市场/行业未来跑赢 | RSP/SPY、IWM/SPY 衡量参与度 | 中 |
| 技术 + 宏观互补 | Neely, Rapach, Tu & Zhou (2014, *Management Science*) | 技术识别顶部、宏观识别底部，组合更优 | 支持「流动性 × 趋势」四象限 | 中强 |
| 可预测性警示 | Welch & Goyal (2008, *RFS*)；Goyal, Welch & Zafirov (2024, *RFS*) | 绝大多数预测变量样本外失效 | 只做环境展示与条件分布 | 强（反面） |
| Fed Model 批评 | Asness (2003, *JPM*) | 名义债券收益率与实际盈利收益率直接比较存在通胀错配 | 现有股债利差补充 10Y 实际利率口径 | 中 |

### 方案草案：「市场大势」面板

六个分项，每项展示当前值、截至当日的滚动历史分位（禁止全样本分位）、13 周方向与数据日期：

| 分项 | 指标（FRED 代码 / 来源） | 频率与发布 | 灯色规则草案（需回测校准） |
|---|---|---|---|
| ① 央行与财政水位 | 净流动性 `WALCL − WTREGEN − RRPONTSYD`（注意单位换算，标注经验口径）、准备金 `WRESBAL` | 周频，周四公布周三数据 | 13 周变化 >0 绿；小幅下降黄；<−1σ 或 SOFR−IORB >0 红 |
| ② 金融条件 | `NFCI`、`ANFCI`（可选 `STLFSI4`） | 周频，周三公布截至上周五，会修订 | <0 且下降绿；>0 或快速上升黄；>0 且快速上升红 |
| ③ 信用利差 | `BAMLH0A0HYM2`；备选 `BAA10Y` | 日频，滞后 1 天 | 中间分位绿；10 年分位 <10% 黄（过热）；13 周走阔 >100bp 或分位 >80% 红 |
| ④ 利率与曲线 | 已有 2Y/10Y；新增财政部 `BC_3MONTH`、`DFII10` 实际利率 | 日频 | 展示 10Y−3M 与纽约联储 probit 概率；倒挂中或解除后 6 个月黄；实际利率 21 日升 >50bp 红 |
| ⑤ 趋势与广度 | 长桥只读 ETF 日线：SPY/QQQ 相对 MA200 与 10 月均线、12-1 动量；RSP/SPY、IWM/SPY、HYG/IEF | 日频（已确认收盘） | 指数在 MA200 上且广度上行绿；广度背离黄；跌破 MA200 且 HYG/IEF 下行红 |
| ⑥ 波动与美元 | `VIXCLS`、VRP ≈ VIX² − (SPY HV20)²、`DTWEXBGS` | 日频，滞后 1 天 | VIX >25 或 VRP <0 红；美元 13 周涨 >5% 黄 |

合成方式：「流动性方向（①②③合成）× 指数趋势（⑤）」四象限——顺风 / 背离（警惕见顶）/ 修复（观察见底）/ 逆风，外加「红灯数 / 6」表述为「下行风险偏高」而非「看空」。可选条件分布卡片：按当前象限或红灯数筛选历史同类日期，展示 SPY 未来 1/3/6 个月收益 P10/中位数/P90 与最大回撤，并标注样本内统计。

与现有系统衔接：新增 `signaldesk/macro.py` 沿用 `research.py` 的 `httpx` 抓取与缓存降级模式；`/api/macro` 与 WebSocket 推送；`fetch_curve()` 增加 3M 并为新字段提供兼容默认值；股债利差补充实际利率口径；`instruments.py` 基金特征复用于大势基准；宏观摘要不含隐私，可经 `safe_snapshot()` 白名单新增 `macro_regime`，Codex 仍纯手动触发。

### 数据诚实与待核对项

- **按发布时间对齐**：H.4.1 周四 16:30 ET 发布周三数据；NFCI 周三发布。看板与回测只能在发布之后使用，禁止按观察日回填。
- **修订**：NFCI 等会修订，回测须用 ALFRED 历史版本。
- **ICE 高收益 OAS 在 FRED 上的历史年限可能受授权限制（未实测）**；不足以计算 10 年分位时改用 `BAA10Y`。
- **长桥能否提供 VIX / 指数行情未验证**，首版用 FRED `VIXCLS`。
- **FRED `fredgraph.csv?id=...` 是否稳定免 key 可用未实测**；备选为免费 FRED API Key，存入本机 DPAPI 凭据库。
- **自选池广度存在选择与幸存者偏差**，只能标为「自选池广度」，不得冒充全市场广度。
- 不建议纳入：M2（月频、样本外不稳）、FINRA 融资余额（月频滞后约 3 周）、0–100 大势总分、用净流动性回归指数点位或「合理估值」。

### 参考文献

- Adrian, Boyarchenko & Giannone (2019). Vulnerable Growth. *AER* 109(4). https://doi.org/10.1257/aer.20161923
- Gilchrist & Zakrajšek (2012). Credit Spreads and Business Cycle Fluctuations. *AER* 102(4). https://doi.org/10.1257/aer.102.4.1692
- López-Salido, Stein & Zakrajšek (2017). Credit-Market Sentiment and the Business Cycle. *QJE* 132(3). https://doi.org/10.1093/qje/qjx014
- Miranda-Agrippino & Rey (2020). U.S. Monetary Policy and the Global Financial Cycle. *REStud* 87(6). https://doi.org/10.1093/restud/rdaa019
- Adrian, Etula & Muir (2014). Financial Intermediaries and the Cross-Section of Asset Returns. *JF* 69(6). https://doi.org/10.1111/jofi.12189
- Brunnermeier & Pedersen (2009). Market Liquidity and Funding Liquidity. *RFS* 22(6). https://doi.org/10.1093/rfs/hhn098
- Amihud (2002). Illiquidity and Stock Returns: Cross-Section and Time-Series Effects. *Journal of Financial Markets* 5(1).
- Avdjiev, Du, Koch & Shin (2019). The Dollar, Bank Leverage, and Deviations from Covered Interest Parity. *AER: Insights* 1(2).
- Copeland, Duffie & Yang (2021). Reserves Were Not So Ample After All. NBER Working Paper 28142.
- Estrella & Mishkin (1998). Predicting U.S. Recessions: Financial Variables as Leading Indicators. *REStat* 80(1).
- Bollerslev, Tauchen & Zhou (2009). Expected Stock Returns and Variance Risk Premia. *RFS* 22(11). https://doi.org/10.1093/rfs/hhp008
- Moreira & Muir (2017). Volatility-Managed Portfolios. *JF* 72(4). https://doi.org/10.1111/jofi.12513
- Moskowitz, Ooi & Pedersen (2012). Time Series Momentum. *JFE* 104(2). https://doi.org/10.1016/j.jfineco.2011.11.003
- Faber (2007). A Quantitative Approach to Tactical Asset Allocation. *Journal of Wealth Management*. SSRN 962461.
- Zaremba, Szyszka, Karathanasopoulos & Mikutowski (2021). Herding for Profits: Market Breadth and the Cross-Section of Global Equity Returns. *Economic Modelling*.
- Neely, Rapach, Tu & Zhou (2014). Forecasting the Equity Risk Premium: The Role of Technical Indicators. *Management Science* 60(7). https://doi.org/10.1287/mnsc.2013.1838
- Welch & Goyal (2008). A Comprehensive Look at the Empirical Performance of Equity Premium Prediction. *RFS* 21(4). https://doi.org/10.1093/rfs/hhm014
- Goyal, Welch & Zafirov (2024). A Comprehensive 2022 Look at the Empirical Performance of Equity Premium Prediction. *RFS*.
- Asness (2003). Fight the Fed Model. *Journal of Portfolio Management* 30(1).
- 数据口径：[Chicago Fed NFCI](https://www.chicagofed.org/research/data/nfci/current-data)、[FRED](https://fred.stlouisfed.org/)、[Fed H.4.1](https://www.federalreserve.gov/releases/h41/)、[纽约联储收益率曲线衰退概率](https://www.newyorkfed.org/research/capital_markets/ycfaq)、[财政部收益率 XML](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed)。

文献结论来自公开摘要与检索综述，卷期页码以出版方页面为准。
