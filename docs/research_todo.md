# SignalDesk 学术对照分析与精简/升级 TODO

生成日期：2026-11-24。本文档结合 2019–2026 年实证资产定价、行为金融与量化风控顶刊研究，逐项对照 SignalDesk 当前规则引擎（`fusion-1.1.0` / `forecast` / `wave_trend` / `macro-1.0.0` / `ext-1.0.0`）与本机已有免费数据源（前复权日线 OHLCV、`SPY/QQQ/RSP/IWM/HYG/IEF` 基准日线、LongPort `CalcIndex`、FRED 14 条宏观序列与美国财政部曲线），给出**可浓缩精简项**、**高信噪比新指标**以及**分阶段可执行 TODO 清单**。

> 核心原则：**只做严格因果、可解释、零新增付费数据源的升级；先减法去共线，再加法补正交，一切权重调整必须通过本地历史回放检验，拒绝拍脑袋调参或引入黑箱模型。**

---

## 一、核心学术证据地图（与本项目直接相关）

| 方向 | 代表文献（含近年后续） | 核心实证结论 | 对 SignalDesk 的直接指导 |
|---|---|---|---|
| **因子冗余与聚类压缩** | Jensen, Kelly & Pedersen (2023, *JF*, "Is There a Replication Crisis in Finance?") | 数百个异象高度共线，可压缩为少数正交经济主题（趋势/动量、低风险、价值、质量/流动性等）；同主题堆叠只会放大噪声，不能提高夏普。 | 合并当前重名且共线的多套评分与短周期震荡指标，改按正交维度展示。 |
| **看板信息过载与过度交易** | Barber, Huang, Odean & Schwarz (2022, *JF*); Barber, Lin & Odean (2024, *JFQA*) | 交易看板上高显著性冲突标签、频繁跳动数字会诱导注意力交易（Attention-Induced Trading），个人投资者追买高注意力股 20 日异常收益约 `-4.7%`。 | 收敛同屏冲突分数（当前同屏出现日线分、评级分、行动标签、波浪标签 4 套信号），降低高频噪音权重。 |
| **传统技术指标 Alpha 衰减** | 2022–2025 实证综述（RSI/MACD/波浪形态有效性衰减） | 默认参数 `RSI(14)`、`MACD(12,26,9)` 在现代机构化美股中存在严重拥挤与假突破；艾略特波浪数浪缺乏样本外稳健统计优势。 | 不再用默认 RSI/MACD 单独驱动重权重打分；波浪保留「道氏高低点+失效位」，数浪降级为辅助参考。 |
| **多周期趋势 & 残差动量 & 52周高点** | Han, Zhou & Zhu (2016, *JFE*); Han, He, Rapach & Zhou (2024, *RoF*); Blitz et al. (2011) 后续; George & Hwang (2004, *JF*) | 多周期均线聚合的 Trend Factor 与剔除大盘 Beta 的**残差动量**夏普率显著高于原始动量；**52 周高点锚定**（`Close/High52w`）稳健捕捉投资者反应不足。 | 用本地已缓存 `SPY` 日线剥离大盘 Beta 算个股残差动量，并将 52 周高点指标从 ETF 推广到全市场个股。 |
| **蛙跳动量 / 信息离散度 (ID)** | Da, Gurun & Warachka (2014, *RFS*); Galvani (2024); Zhang et al. (2026) | 连续小幅上涨（低 `ID`）的趋势延续性远强于靠少数暴涨日推高的脉冲行情（高 `ID`）；`ID` 在熊市急剧升高并解释动量崩盘。 | 纯日线 3 行公式算出 `ID`，一眼区分「稳步慢牛」与「事件脉冲防追高」。 |
| **隔夜 vs 日内拉锯战** | Lou, Polk & Skouras (2019, *JFE*; 2022–2025 后续 *The Day Destroys the Night*); Bogousslavsky (2021, *JFE*); NY Fed Overnight Drift | 动量溢价高度集中于隔夜（Close→Open），而日内（Open→Close）常呈现机构反向均值回归；客户群体分化导致部分标的长期「高开低走」。 | 利用日线 `open`/`close` 拆解 20/60 日隔夜 vs 日内累计收益，与现有夜盘/盘前动态形成黄金联动。 |
| **彩票效应 (MAX) 与尾部下行风险** | Bali, Cakici & Whitelaw (2011, *JFE*) 及 2022–2025 复现; Ang, Chen & Xing (2006, *RFS*); Amaya et al. (2015, *JFE*) | 近 1 月极端单日大涨（`MAX`）显著预测未来跑输（并解释大部分 IVOL 异象）；**下行贝塔**与**已实现偏度**刻画大盘暴跌时的真实脆弱性。 | 将粗糙的 `ATR/price > 4%` 升级为 `MAX5` 彩票过热、`Downside Beta` 抗跌度与 `Realized Skewness` 尾部风险。 |
| **波动率管理与移动止损** | Barroso & Santa-Clara (2015, *JFE*); Moreira & Muir (2017, *JF*) 2022–2025 Yang-Zhang 改进; Kaminski & Lo (2014); Han, Zhou & Zhu (2016) | 用 **Yang-Zhang 波动率**（含隔夜跳空）按波动反向调节敞口可显著削峰填谷；基于峰值的**移动止损（Trailing Stop）**可将动量左尾崩盘转为正偏度。 | 用 Yang-Zhang 替代普通收盘 HV；补充「波动率参考仓位系数」与持仓盈利后的动态移动止损线。 |
| **流动性摩擦与换手过热** | Amihud (2002, *JFM*) 及 2022–2025 Realized Illiquidity 研究 | 价格冲击成本（`|r|/DollarVol`）与异常换手率能有效识别冷门滑点股与散户过热拥挤股。 | 复用日线算 `Amihud`，顺带拉取 LongPort 免费 `TurnoverRate` 与 `TotalMarketValue`（零额外请求）。 |
| **样本外检验红线** | Welch & Goyal (2008, *RFS*); Goyal, Welch & Zafirov (2024, *RFS*) | 超过三分之一的新发表变量在样本外迅速失效；禁止凭直觉硬编码复杂加权规则而不做历史回放校验。 | 升级 `signaldesk/replay.py` 为多股因果回放评测脚本（IC / 分层收益 / 回撤截断），先验后上。 |

---

## 二、现有功能诊断：可以浓缩精简什么（做减法）

### 1. 消除「同屏 4 套重叠评分/结论」的认知割裂
- **现状问题**：当前选中一只股票时，屏幕同时出现 `verdict` 行动标签（如 `震荡观望`）、`forecast` 评级分（如 `中性观望 51.5分`）、`indicators` 日线分（如 `42.6分`）与 `wave_trend` 趋势结论（如 `下降趋势`），且 `forecast` 的 40% 直接嵌套了 `indicators` 的日线分，另外 10% 风险控制又对 `indicators` 已算过的 `RSI` / `MA20 偏离` 再次扣分（**双重计票**）。
- **精简方向**：
  - 将「日线结构评分」与「5 级买卖评级」在信息层级上合二为一：主视图只保留**唯一主评分与清晰行动定位**，原「日线结构评分」卡片可浓缩合并进主评分的「趋势动量因子拆解」或默认归类为次级明细模块。
  - 消除重复计票：风控护栏（如跌破失效价、负 PE、空头弱势、彩票过热）统一只作为「独立风控门控 / 评级封顶」生效，不再一边在因子分里扣分、一边又在风控分里二次扣分。

### 2. 降权并改造高噪音的「单日量价分（占日线总分 30%）」
- **现状问题**：[indicators.py](../signaldesk/indicators.py) 第 141 行 `volume_score = sign(return_1) * clip(RVOL - 1, 0, 1)` 权重高达 **30%**。只要某一天收盘微跌 `-0.1%` 且成交量略高于 20 日均量 2 倍，量价分就直接砸到 `0`，导致日线总分单日剧烈跳变 ±15 分，严重违背「长期复核、抗噪音」初衷。
- **精简方向**：取消单日涨跌 × 单日 RVOL 的 30% 暴躁打分；改为**平滑多日量价确认（如 5–20 日量价协同 + 换手/流动性过滤）**，并将权重下调至 `10%–15%`（或转为确认过滤器而非主驱动分）。

### 3. 精简高度共线的短周期冗余原始算子
- **现状问题**：`indicators.py` 中 `RSI14`、`MACD_hist`、`zscore20`、`rank20`、`corr20` 五个指标都挤在 14–20 日短窗口内，相互相关性极高（且 `zscore20`、`rank20`、`corr20` 仅展示在折叠字典里，从未参与核心决策，属于纯展示冗余）。
- **精简方向**：
  - 剔除或下沉冗余的 `zscore20 / rank20 / corr20`（除非回放证明某项具有独立增量 IC）；
  - 将 `EMA20/EMA50/MA200` + `RSI/MACD` 浓缩升级为正交的**「多周期趋势（Trend Factor 思想）+ 残差动量（相对 SPY）+ 信息连续度（ID）」**，信噪比更高、维度更清晰。

### 4. 重新定位「艾略特波浪数浪」与「点位锚点堆叠」
- **现状问题**：
  - [wave_trend.py](../signaldesk/wave_trend.py) 同时产出「道氏结构 + 平行趋势通道 + 突破/失效位」（**高实用价值**）和「1–5 浪 / A–C 浪数浪 + 斐波那契测算」（**学术证据弱、易随新 K 线切换浪型**）。
  - [forecast.py](../signaldesk/forecast.py) 的 5 档买卖价位候选池同时混入了 MA20/EMA20/BOLL中轨（三者几乎重合）与 20日枢轴 `S1/R1`、斐波那契 1.618，锚点看似丰富实则彼此重叠。
- **精简方向**：
  - 趋势模块突出**「趋势通道 + 道氏结构 + 明确突破位/失效位」**为核心；艾略特 1–5 浪编号与斐波那契目标保留为二级辅助参考标注（且不进入自动化买卖评级打分）。
  - 点位锚点去重：合并几乎重合的 `MA20 / EMA20 / BOLL中轨` 为单一「20 日趋势中枢」，用 **Yang-Zhang 波动率 / ATR 通道 + 真实前高前低（结构位）** 作为核心支撑阻力锚，更干净稳定。

### 5. 审视并精简 15 分钟分时回放残留复杂度
- **现状问题**：看板已明确主攻「美股长期复核 + 日线结构 + 盘外动态」，但 `indicators.py` 与 `app.py` 仍维护着一套较重的 `15m` 分时会话切分与时段基线逻辑（仅用于离线 CSV 回放与少量旧测试）。
- **精简方向**：保持 `replay.py` 接口兼容的同时，将线上服务路径明确聚焦于「已确认前复权日线 + 当日实时 K 线 + 盘外独立通道」，避免为低频使用的 15m 逻辑增加实时链路维护负担。

---

## 三、建议新增的高有效指标（全部零新增付费数据）

所有候选指标仅依赖**本机已有前复权 OHLCV + 已缓存 `SPY` 日线 + LongPort 免费 `CalcIndex`**，按「学术强度 × 工程性价比」排序：

1. **残差动量（`ResidualMom_12_1`）与相对强弱（vs `SPY`）**
   - 计算：基于近 126–252 个共同交易日，对个股日对数收益与 `SPY` 做因果 OLS 回归得到特质残差 $\varepsilon_{i,t}$，取 `t-252` 至 `t-21`（剔除近 1 个月短线反转）的标准化累计残差收益。
   - 价值：彻底区分「真 Alpha 强势股」与「纯跟大盘涨的 Beta 股」，大幅降低市场风格切换时的动量崩盘。
2. **蛙跳动量 / 信息离散度（`FIP / ID`）**
   - 计算：$ID = \text{sign}(R_{12\text{-}1}) \times (\%\text{下跌日} - \%\text{上涨日})$（或同步计算 60 日中短周期 `ID60`）。
   - 价值：识别「慢牛连续上涨（低 ID，高质量趋势）」vs「单日暴涨脉冲（高 ID，谨防回调）」，直接提升买卖时机判断质量。
3. **52 周高点锚定（`52W High Proximity`）全标的统一化**
   - 计算：`close / high_52w`（目前已在 `instruments.py` 给 ETF 算过，直接复用到全部个股）。
   - 价值：学术界复现率最高的行为金融动量指标之一；直观反映筹码套牢压力与突破空间。
4. **隔夜 vs 日内收益拆解（`Overnight / Intraday Tug-of-War`）**
   - 计算：基于前复权日线 `open_t` 与 `close_{t-1}`，统计近 20 日 / 60 日累计隔夜收益 $\prod (O_t / C_{t-1}) - 1$ 与累计日内收益 $\prod (C_t / O_t) - 1$。
   - 价值：与 SignalDesk 现有的夜盘/盘前动态完美结合！当某股近 20 日呈现「隔夜拉涨、日内连阴派发」时，在夜盘/盘前大涨时主动发出「历史高开低走特征，谨防开盘追高」提醒。
5. **三维精准风险画像：`MAX5`（彩票过热）+ `Downside Beta`（下跌贝塔）+ `Yang-Zhang 波动率`**
   - 计算：
     - `MAX5`：近 21 个交易日排名前 5 高单日涨幅的均值（超过阈值触发「彩票型过热/谨防追高」护栏）；
     - `Downside Beta`：近 126 日中仅在 `SPY` 下跌日的个股相对 `SPY` 敏感度；
     - `Yang-Zhang HV`：融合隔夜跳空方差、开收方差与 Rogers-Satchell 日内方差的无偏最小方差波动率估计。
   - 价值：比 `ATR/price > 4%` 精准一个量级，专门拦住「暴涨妖股追高」与「大盘微跌它暴跌」两类个人投资者最大亏损源。
6. **波动率管理仓位参考系数 + 持仓移动止损（`Vol-Managed Sizing & Trailing Stop`）**
   - 计算：
     - 仓位参考系数 = `clip(目标波动 20% / Yang-Zhang HV60, 0.25, 1.5)`，并结合 `macro.py` 宏观红灯水位（红灯 `>= 4/6` 时展示保守风险预算乘数，例如 `×0.7`）；
     - 持仓盈利标的自动测算动态峰值回撤止损（`Trailing Stop = max(入场以来或近60日峰值 × (1 - 2.5×ATR%), 固定失效价)`），纯参考不下单。
   - 价值：把 `macro.py`（宏观底色）与个股风控以**严谨、克制、不乱改买卖方向**的方式真正联动起来（呼应 Moreira & Muir 2017、Han/Zhou/Zhu 2016 止损研究）。
7. **流动性冲击（`Amihud`）与换手率/总市值（LongPort 免费 `CalcIndex`）**
   - 计算：`Amihud_20d = mean(|r_t| / dollar_volume_t)`；同时在 `providers.py` 的 `valuations()` 批量调用中顺带加入 `CalcIndex.TurnoverRate` 与 `CalcIndex.TotalMarketValue`（零额外 API 调用）。
   - 价值：识别低流动性高滑点小盘股与异常高换手情绪顶。

---

## 四、分阶段可执行 TODO 清单

### Phase 0：因果回放评测基准（先验后改，杜绝拍脑袋调参）
- [x] **P0-1 扩展本地多股回放验证工具**（[factor_eval.py](../signaldesk/factor_eval.py)）
  - 利用本机 SQLite `live-fwd-v3` 中已同步的 90+ 只前复权美股日线 + `macro-live-fwd-v3` 中的 `SPY` 日线，做严格时点因果 Walk-Forward 回测。
  - 输出每个旧因子（趋势/动量/单日量价/RSI/MACD/zscore20/rank20/corr20）与每个新候选因子（残差动量、52W High、FIP/ID、隔夜-日内差、MAX5、Downside Beta、Yang-Zhang HV、Amihud）在未来 5 / 20 / 60 个交易日的：
    - 滚动横截面 RankIC 与 ICIR；
    - 因子两两相关性矩阵（量化实证共线度，为砍掉冗余指标提供铁证）；
    - 多头分层收益、最大回撤与移动止损前后偏度对比。
- [x] **P0-2 输出实证裁剪报告**：基于本机实盘池 3–4 年前复权数据确认最终保留的精简特征集与合理权重区间，记录到 [docs/research.md](./research.md)。

### Phase 1：做减法——指标去重、降噪与信息层级浓缩（核心提纯）
- [x] **P1-1 改造高噪音单日量价分（`fusion-2.0.0` 规则升级）**（[indicators.py](../signaldesk/indicators.py)）
  - 废除「单日涨跌 × 单日 RVOL 占总分 30%」的暴躁算法，改为多日平滑量价确认（权重降至 `<= 15%`）并结合换手/流动性门控。
  - 移除或下沉高共线、低增量的 `zscore20` / `rank20` / `corr20`（视 P0 回放结果定夺）。
- [x] **P1-2 消除「日线分 vs 评级分 vs 行动标签」多重打架与二次扣分**（[forecast.py](../signaldesk/forecast.py)、[service.py](../signaldesk/service.py)）
  - 统一「唯一主评分 + 正交证据维度」，避免同一只股票顶部同时出现 3 个不同数值的分数。
  - 将风控项统一收口为「独立风控门控/封顶」，避免在技术分和风控分里重复惩罚同一个 RSI/偏离条件。
- [x] **P1-3 精简点位锚点候选池 & 弱化主观数浪权重**（[forecast.py](../signaldesk/forecast.py)、[wave_trend.py](../signaldesk/wave_trend.py)）
  - 合并重合的 `MA20 / EMA20 / BOLL中轨` 锚点，收敛为「结构位（前高前低）+ 波动通道」清晰锚点。
  - `WaveTrendSection` 一级界面主推「趋势方向 + 通道位置 + 明确突破位/前低失效位」，将艾略特 1–5 浪编号作为可选折叠辅助标签。

### Phase 2：做加法——零成本接入高有效学术因子（纯用现有免费数据源）
- [x] **P2-1 上线「残差动量 + 52 周高点 + 信息离散度 (ID)」趋势质量组**
  - 新建纯因果因子模块 [factors.py](../signaldesk/factors.py)（全单测覆盖零未来函数、缺口切断与 NaN 防御）。
  - 复用已缓存 `SPY` 日线计算 `residual_mom_z`（近 12-1 月剥离 Beta 不扣自身 Alpha 的超额动量信息比）、`high_52w_ratio`（全标的统一）与 `info_discreteness`（FIP 慢牛 vs 脉冲判定）。
  - 将这三项纳入 `fusion-2.0.0` 评分或「买卖点位评级」的核心趋势质量证据。
- [x] **P2-2 上线「隔夜 vs 日内拉锯战」诊断并与盘外动态联动**（[extended_hours.py](../signaldesk/extended_hours.py)）
  - 基于前复权日线计算近 20 日 / 60 日累计隔夜收益与日内收益、隔夜/日内胜率差。
  - 在「盘外动态」模块中增加一句话行为定性：例如当某股近 20 日隔夜累计 `+12%` 而日内累计 `-9%` 时，在夜盘/盘前拉涨时主动警示「近 20 日呈高开低走特征，谨防开盘追高」。
- [x] **P2-3 上线「三维精准风控画像」：`MAX5` + `Downside Beta` + `Yang-Zhang 波动率`**（[factors.py](../signaldesk/factors.py)、[instruments.py](../signaldesk/instruments.py)、[forecast.py](../signaldesk/forecast.py)）
  - 用 **Yang-Zhang 无偏波动率**升级现有简单收盘 `HV20 / HV60`，真实计入财报/隔夜跳空波动。
  - 新增 `MAX5` 彩票过热检测（当近月最大 5 日均涨超阈值时触发独立风控护栏，防止追买情绪顶）。
  - 新增 `Downside Beta`（大盘下跌日敏感度），在「独立风险检查」与宏观逆风环境里高亮高脆弱性持仓。
- [x] **P2-4 零成本扩展 LongPort `CalcIndex` 免费字段与 Amihud 流动性**（[providers.py](../signaldesk/providers.py)）
  - 在现有 `valuations()` 批量拉取中追加 `CalcIndex.TurnoverRate`（换手率）与 `CalcIndex.TotalMarketValue`（总市值），零额外 API 请求。
  - 结合日线 `Amihud_20d` 非流动性指标，为小盘/高冲击成本/异常换手标的提供滑点与拥挤警示。

### Phase 3：风险预算闭环与看板交互精炼（宏观-个股克制联动）
- [x] **P3-1 新增「波动率参考仓位系数」与「盈利移动止损（Trailing Stop）」**（[forecast.py](../signaldesk/forecast.py)、[StockInspector.tsx](../frontend/src/StockInspector.tsx)）
  - 基于 Yang-Zhang 波动率给出纯参考性的相对仓位系数（目标年化波动基准），并在 `macro.py` 红灯数 `>= 4/6`（逆风/高尾部风险）时联动展示宏观保守折算系数（例如 `宏观逆风建议降敞口 ×0.7`），只做风险预算提示、绝不扭曲个股客观价格结构。
  - 对已有标的自动在「长期计划价位」补充近 60 日峰值 `2.5×ATR14` 客观移动止损保护线及一键采纳入口（防盈利大幅回吐）。
- [x] **P3-2 接入脱敏 Codex 快照与右侧模块配置**（[security.py](../signaldesk/security.py)、[inspectorModules.ts](../frontend/src/inspectorModules.ts)）
  - 将新增的脱敏指标（残差动量、ID 连续度、隔夜-日内特征、MAX5、Downside Beta、Yang-Zhang 波动率与宏观风险预算系数）纳入 `safe_snapshot()` 白名单，提升手动复核的专业深度，同时严守零持仓金额/股数隐私边界。
  - 配合右侧模块化自定义面板，保持默认首屏极致精简，让高级因子拆解按需展开或自由开关。

### Phase 4：全量验收与文档同步
- [x] **P4-1 自动化测试覆盖**：为每个新因子编写严格因果性测试（截断未来 K 线后历史时点结果完全一致）、断档/NaN 边界测试与拆股前复权回归测试，确保 `pytest` 全量通过。
- [x] **P4-2 规则版本与文档归档**：升级 `RULE_VERSION` 为 `fusion-2.0.0`，完整更新 [docs/signals.md](./signals.md)、[docs/research.md](./research.md) 与 [docs/verification.md](./verification.md)，并完成 16:9 实盘浏览器验收。

---

## 五、参考文献（新增补充）

- Jensen, T. I., Kelly, B. T., & Pedersen, L. H. (2023). Is There a Replication Crisis in Finance? *The Journal of Finance*, 78(5), 2465–2518.
- Barber, B. M., Huang, X., Odean, T., & Schwarz, C. (2022). Attention-Induced Trading and Returns: Evidence from Robinhood Users. *The Journal of Finance*, 77(6), 3141–3190.
- Barber, B. M., Lin, S., & Odean, T. (2024). Resolving a Paradox: Retail Trades Positively Predict Returns but Are Not Profitable. *Journal of Financial and Quantitative Analysis*.
- Han, Y., He, A., Rapach, D. E., & Zhou, G. (2024). Cross-Sectional Expected Returns: New Fama–MacBeth Regressions in the Era of Machine Learning. *Review of Finance*.
- Han, Y., Zhou, G., & Zhu, Y. (2016). A Trend Factor: Any Economic Gains from Using Information over Investment Horizons? *Journal of Financial Economics*, 122(2), 352–375.
- Han, Y., Zhou, G., & Zhu, Y. (2016). Taming Momentum Crashes: A Simple Stop-Loss Strategy. SSRN Working Paper.
- Kaminski, K. M., & Lo, A. W. (2014). When Do Stop-Loss Rules Stop Losses? *Journal of Financial Markets*, 18, 234–254.
- Da, Z., Gurun, U. G., & Warachka, M. (2014). Frog in the Pan: Continuous Information and Momentum. *Review of Financial Studies*, 27(7), 2171–2218.（及 Galvani 2024 市场状态交互研究、Zhang et al. 2026 市场级 ID 预测研究）
- Blitz, D., Huij, J., & Martens, M. (2011). Residual Momentum. *Journal of Empirical Finance*, 18(3), 506–521.（及近年因子动量剥离后续研究）
- George, T. J., & Hwang, C.-Y. (2004). The 52-Week High and Momentum Investing. *The Journal of Finance*, 59(5), 2145–2176.
- Lou, D., Polk, C., & Skouras, S. (2019). A Tug of War: Overnight Versus Intraday Expected Returns. *Journal of Financial Economics*, 134(1), 192–213.（及作者 2022–2025 后续工作论文 *The Day Destroys the Night, Night Extends the Day*）
- Bogousslavsky, V. (2021). The Cross-Section of Intraday and Overnight Returns. *Journal of Financial Economics*, 141(1), 172–194.
- Bali, T. G., Cakici, N., & Whitelaw, R. F. (2011). Maxing Out: Stocks as Lotteries and the Cross-Section of Expected Returns. *Journal of Financial Economics*, 99(2), 427–446.
- Ang, A., Chen, J., & Xing, Y. (2006). Downside Risk. *Review of Financial Studies*, 19(4), 1191–1239.
- Amaya, D., Christoffersen, P., Jacobs, K., & Vasquez, A. (2015). Does Realized Skewness Predict the Cross-Section of Equity Returns? *Journal of Financial Economics*, 118(1), 135–167.
- Yang, D., & Zhang, Q. (2000). Drift-Independent Volatility Estimation Based on High, Low, Open, and Close Prices. *The Journal of Business*, 73(3), 477–492.（及 2022–2025 波动率管理组合应用研究）
- Barroso, P., & Santa-Clara, P. (2015). Momentum Has Its Moments. *Journal of Financial Economics*, 116(1), 111–120.
- Moreira, A., & Muir, T. (2017). Volatility-Managed Portfolios. *The Journal of Finance*, 72(4), 1611–1644.
- Goyal, A., Welch, I., & Zafirov, A. (2024). A Comprehensive 2022 Look at the Empirical Performance of Equity Premium Prediction. *Review of Financial Studies*.
