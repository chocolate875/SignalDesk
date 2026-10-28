# 算子、因子与提醒口径

核心公式版本 `fusion-1.0.0`。输出附加当前规则配置的SHA-256短指纹；每个事件记录公式版本、数据时间和维度证据。公式是可解释的技术结构描述，不是预测概率或经过收益优化的交易策略。

## 数据前提

- OHLCV按UTC时间排序并去重；只使用明确已确认且结束时间不晚于当前时刻的K线。
- 日线使用常规交易时段；15分钟序列按 regular/pre/post/overnight 独立计算，避免把薄弱盘外量与盘中混算。
- 指标口径采用ta 0.11.0、fillna=False。ATR的前13根库前置零值额外屏蔽，零ATR视为不可用。
- 无效OHLCV和同交易日内分时缺口会切断计算段并重新预热。缺数据不前向填充、不补零、不重新分配缺失维度权重。
- 最晚应完成K线由XNYS交易日历、时段和提前收盘规则计算；超过90秒容差的缺口标为过期。实时关键价还要求报价时间在最近120秒内。
- 半日盘盘后采用17:00纽约时间的本机保守日历边界；具体证券可用性以LongPort推送与权限为准。SDK返回的交易日/半日盘信息另外保存在本机，可供核对。

## 白名单算子

`delay(x,n)`、`delta(x,n)`、`returns(x,n)`只允许正整数历史窗口；`mean/std/min/max`要求完整窗口，标准差使用ddof=0；`ts_rank`采用平均秩百分位；`zscore`在零方差时返回NaN；`corr`按相同时间索引对齐；`clip`限制输出范围。不提供eval、动态导入和任意脚本执行。

## 默认融合公式

记 `clip(x)=min(1,max(-1,x))`，每个原始维度位于[-1,1]，映射为 `D=50*(1+d)`：

```
t1 = clip((EMA20 - EMA50) / ATR14)
t2 = clip((EMA20 - delay(EMA20, 5)) / ATR14)
t3 = sign(close - MA200)
trend_raw = (t1 + t2 + t3) / 3

m1 = (RSI14 - 50) / 50
m2 = clip(MACD_hist / ATR14)
momentum_raw = (m1 + m2) / 2

volume_raw = sign(returns(close, 1)) * clip(RVOL - 1, 0, 1)

score = 0.40 * trend + 0.30 * momentum + 0.30 * volume_score
```

RVOL日线基准为此前20个已完成交易日的成交量均值；分时基准为同一交易时段、纽约本地相同15分钟位置、此前最多20个交易日的成交量均值，至少10个有效历史样本。当前K线不进入自身基准。

分时VWAP按交易日和时段重置，用累计成交额/累计成交量；没有成交额的回放CSV只能得到近似值。日线单根OHLC不被冒充为盘中VWAP，显示为空。

默认70及以上为偏强、30及以下为偏弱，其余为中性。融合区间变化还要求至少两个维度同向确认：偏强对应维度>=60，偏弱对应<=40。同类指标先汇总，不为多条均线重复计票。

## 独立风险与通知

波动偏高(ATR/price>4%)、偏离MA20超过2ATR、RSI极值、停牌、数据缺失和盘外流动性分别展示。盘外机会额外要求价差<=0.5%、完整15分钟成交额>=100万美元；缺盘口不能自动通过。风险事件不会被机会过滤器压掉。

普通融合事件按同股/仓位类别/周期/时段状态变化产生，同类冷却30分钟，状态及冷却跨重启保存。首次加载建立基线；重连补齐的旧K线标为历史事件，不作为新机会。实时关键价独立判断，双类别持仓优先关联短线部分。

长期仓普通变化进入收盘后10分钟摘要，结构转弱和关键价风险及时处理。短线普通事件即时进入本机通知；QQ普通事件等待30秒收集并合并，重要风险优先发送。暂停普通提醒后重要风险仍继续。

## 回放

```
.venv\Scripts\python.exe -m signaldesk.replay --output .runtime\replay-demo.json
.venv\Scripts\python.exe -m signaldesk.replay --input data\bars.csv --symbol AAPL.US --timeframe 15m --session regular --output .runtime\replay.json
```

CSV必需列：timestamp(带时区ISO8601)、open、high、low、close、volume；可选turnover、session、confirmed。JSON使用相同字段的数组。文件始终本机读取。报告包含有效窗口与事件列表，不生成账户收益或策略收益结论。
