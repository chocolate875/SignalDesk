import {
  ArrowDown,
  ArrowDownRight,
  ArrowUp,
  ArrowUpRight,
  Bell,
  Bot,
  Check,
  ChevronDown,
  CircleDot,
  Eye,
  Gauge,
  GripVertical,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TriangleAlert,
  X,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import WaveTrendCard from "./WaveTrendSection";
import {
  DEFAULT_INSPECTOR_ORDER,
  INSPECTOR_MODULE_MAP,
  useInspectorLayout,
  type InspectorLayoutConfig,
  type InspectorModuleId,
} from "./inspectorModules";
import {
  fmt,
  labels,
  ticker,
  time,
  type Analysis,
  type Dashboard,
  type EvalMode,
  type LiveEvaluation,
  type Signal,
  type Stock,
  type Summary,
} from "./types";

export type InspectorTab = "summary" | "codex" | "events";

const dimensionNames: Record<string, string> = {
  trend: "趋势",
  momentum: "动量",
  volume_score: "量价",
};

const dimensionColors: Record<string, string> = {
  trend: "#1e40af",
  momentum: "#3b82f6",
  volume_score: "#10b981",
};

const scoreTone = (score: number | null | undefined, state?: string) =>
  state
    ? ({
        strong: "positive",
        weak: "negative",
        neutral: "neutral",
        unavailable: "muted",
      }[state] ?? "muted")
    : score == null
      ? "muted"
      : score >= 70
        ? "positive"
        : score <= 30
          ? "negative"
          : "neutral";

function PlanRangeBar({
  stock,
  onEditPlan,
}: {
  stock: Stock;
  onEditPlan: () => void;
}) {
  const stop = stock.long_plan?.stop ?? null;
  const target = stock.long_plan?.target ?? null;
  const close = stock.long_plan?.close ?? stock.quote?.last ?? null;
  const cost =
    stock.broker_quantity > 0 && stock.cost_price != null
      ? stock.cost_price
      : null;

  const stopDist = stock.long_plan?.stop_distance_percent;
  const targetDist = stock.long_plan?.target_distance_percent;

  const points = [stop, cost, close, target].filter(
    (v): v is number => v != null && Number.isFinite(v),
  );

  let stopPct: number | null = null;
  let targetPct: number | null = null;
  let closePct: number | null = null;
  let costPct: number | null = null;

  if (points.length >= 2) {
    const minV = Math.min(...points);
    const maxV = Math.max(...points);
    const span = Math.max(maxV - minV, (close ?? maxV) * 0.04, 1);
    const lo = minV - span * 0.1;
    const hi = maxV + span * 0.1;
    const pos = (v: number | null) =>
      v == null ? null : Math.max(4, Math.min(96, ((v - lo) / (hi - lo)) * 100));
    stopPct = pos(stop);
    targetPct = pos(target);
    closePct = pos(close);
    costPct = pos(cost);
  }

  return (
    <section className="insp-card">
      <div className="insp-card-head">
        <h3>长期计划价位</h3>
        <button type="button" className="text-btn" onClick={onEditPlan}>
          <SlidersHorizontal size={14} />
          编辑计划
        </button>
      </div>

      {stop != null || target != null ? (
        <>
          <div className="plan-track-wrap">
            <div className="plan-track">
              {stopPct != null && targetPct != null && (
                <div
                  className="plan-zone"
                  style={{
                    left: `${Math.min(stopPct, targetPct)}%`,
                    width: `${Math.abs(targetPct - stopPct)}%`,
                  }}
                />
              )}
              {stopPct != null && (
                <span
                  className="plan-pin pin-stop"
                  style={{ left: `${stopPct}%` }}
                  title={`失效价 $${fmt(stop, 2)}`}
                />
              )}
              {costPct != null && (
                <span
                  className="plan-pin pin-cost"
                  style={{ left: `${costPct}%` }}
                  title={`持仓成本 $${fmt(cost, 2)}`}
                />
              )}
              {targetPct != null && (
                <span
                  className="plan-pin pin-target"
                  style={{ left: `${targetPct}%` }}
                  title={`目标价 $${fmt(target, 2)}`}
                />
              )}
              {closePct != null && (
                <span
                  className="plan-pin pin-close"
                  style={{ left: `${closePct}%` }}
                  title={`已确认收盘 $${fmt(close, 2)}`}
                />
              )}
            </div>
          </div>

          <div className="plan-levels-grid">
            <div className="plan-level-box">
              <small>
                <i className="dot stop" /> 计划失效价
              </small>
              <strong>{stop != null ? `$${fmt(stop, 2)}` : "未设置"}</strong>
              <span>
                {stopDist != null
                  ? stopDist >= 0
                    ? `高于失效价 +${fmt(stopDist, 1)}%`
                    : `低于失效价 ${fmt(stopDist, 1)}%`
                  : "跌破即复核"}
              </span>
            </div>
            <div className="plan-level-box">
              <small>
                <i className="dot close" /> 常规收盘
              </small>
              <strong>{close != null ? `$${fmt(close, 2)}` : "—"}</strong>
              <span>
                {cost != null
                  ? `成本 $${fmt(cost, 2)}`
                  : stock.long_plan.status}
              </span>
            </div>
            <div className="plan-level-box">
              <small>
                <i className="dot target" /> 目标观察价
              </small>
              <strong>{target != null ? `$${fmt(target, 2)}` : "未设置"}</strong>
              <span>
                {targetDist != null
                  ? targetDist >= 0
                    ? `已超目标 +${fmt(targetDist, 1)}%`
                    : `距目标 ${fmt(targetDist, 1)}%`
                  : "到达即复核"}
              </span>
            </div>
          </div>
        </>
      ) : (
        <div className="plan-empty-box">
          <p>
            尚未设置长期失效价与目标价。设定后可在K线图直观显示价位线，并在盘中触价与收盘时自动复核。
          </p>
          <button
            type="button"
            className="button secondary"
            onClick={onEditPlan}
          >
            设置计划价位
          </button>
        </div>
      )}
    </section>
  );
}

function ExtendedHoursCard({ stock }: { stock: Stock }) {
  const ext = stock.extended_hours;
  if (!ext || !ext.available || ext.price == null) return null;

  const isLive = Boolean(ext.is_live_session);
  const tone = !isLive
    ? "muted"
    : ext.alert_level === "danger"
      ? "danger"
      : ext.alert_level === "warning"
        ? "warning"
        : ext.alert_level === "positive"
          ? "positive"
          : ext.liquid
            ? "neutral"
            : "muted";

  const gapText =
    ext.gap_pct != null
      ? `${ext.gap_pct >= 0 ? "+" : ""}${fmt(ext.gap_pct, 1)}%`
      : "";

  const shortTag = !isLive
    ? "已转盘中"
    : !ext.liquid
      ? `${ext.active_label ?? "盘外"}·偏薄`
      : ext.alert_level === "danger"
        ? `${ext.active_label ?? "盘外"}警示`
        : ext.alert_level === "warning"
          ? `${ext.active_label ?? "盘外"}异动`
          : ext.alert_level === "positive"
            ? `${ext.active_label ?? "盘外"}走强`
            : `${ext.active_label ?? "盘外"}平稳`;

  const conclusion = (() => {
    if (!isLive) {
      return `今晨${ext.active_label ?? "盘前"}参考 $${fmt(ext.price, 2)}${
        gapText ? `（${gapText}）` : ""
      }，当前以常规盘中实时走势为准。`;
    }
    if (ext.triggers.length > 0) {
      const main = ext.triggers[0];
      return !ext.liquid
        ? `${main}；成交偏薄（${ext.turnover_text}），谨防虚晃。`
        : `${main}。`;
    }
    return `${ext.active_label ?? "盘外"} $${fmt(ext.price, 2)}${
      gapText ? `（${gapText}）` : ""
    }，成交额 ${ext.turnover_text}（${ext.liquidity_label}），波动平稳。`;
  })();

  const orderedSessions = (["overnight", "pre", "post"] as const)
    .map((k) => ext.sessions?.[k])
    .filter((item): item is NonNullable<typeof item> => Boolean(item));

  return (
    <section
      className={`insp-card ext-card-compact tone-${tone}`}
      aria-label="盘外动态结论"
    >
      <div className="insp-card-head">
        <h3>盘外动态</h3>
        <span className={`verdict-chip tone-${tone}`}>{shortTag}</span>
      </div>
      <p className="ext-concise-line">{conclusion}</p>
      {isLive && ext.triggers.length > 1 && (
        <p className="ext-concise-sub">{ext.triggers[1]}</p>
      )}
      {orderedSessions.length > 0 && (
        <details className="ext-mini-details">
          <summary>
            <span>展开夜盘 / 盘前 / 盘后明细</span>
            <ChevronDown size={14} />
          </summary>
          <div className="ext-session-grid">
            {orderedSessions.map((s) => {
              const isAct = s.session === ext.active_session && isLive;
              const sessTag = isAct
                ? "当前"
                : s.timestamp
                  ? time(s.timestamp, "America/New_York").slice(5, 10)
                  : "上日";
              return (
                <div
                  key={s.session}
                  className={`ext-session-cell ${isAct ? "active" : ""} ${
                    s.is_fresh ? "" : "stale"
                  }`}
                >
                  <div className="ext-sc-head">
                    <span>{s.label}</span>
                    <em>{sessTag}</em>
                  </div>
                  <strong>${fmt(s.price, 2)}</strong>
                  <small
                    className={
                      s.gap_pct == null
                        ? "muted"
                        : s.gap_pct >= 0
                          ? "quote-up"
                          : "quote-down"
                    }
                  >
                    {s.gap_pct != null
                      ? `${s.gap_pct >= 0 ? "+" : ""}${fmt(s.gap_pct, 2)}%`
                      : "—"}
                  </small>
                  <span className="ext-sc-turn">额 {s.turnover_text}</span>
                </div>
              );
            })}
          </div>
          <p className="forecast-disclaimer">
            {ext.source} · {time(ext.timestamp)} · 仅作盘外参考，不计入日线与评级。
          </p>
        </details>
      )}
    </section>
  );
}

function ForecastCard({
  stock,
  onApplyForecastLevels,
}: {
  stock: Stock;
  onApplyForecastLevels: (stopLoss: number, sellLow: number) => void;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const forecast = stock.forecast;
  const rating = forecast?.rating;
  const levels = forecast?.levels;
  const available = Boolean(
    forecast && levels?.available && rating?.available,
  );
  const guardrailCount = rating?.guardrails?.length ?? 0;

  return (
    <section className="insp-card forecast-card">
      <div className="insp-card-head">
        <h3>买卖评级与点位预测</h3>
        <div className="forecast-head-badges">
          <span className={`verdict-chip tone-${rating?.tone ?? "muted"}`}>
            {rating?.label ?? "暂不评级"}
            {rating?.score != null ? ` ${fmt(rating.score, 1)}分` : ""}
          </span>
        </div>
      </div>

      {!available ? (
        <div className="forecast-unavail">
          <p>
            {levels?.reason ||
              rating?.summary ||
              "已确认日线窗口或波动率数据不足，暂不生成点位预测。"}
          </p>
        </div>
      ) : (
        <>
          <div className="forecast-levels-grid">
            <div className="forecast-level-cell buy">
              <small>参考买点区间</small>
              <strong>
                ${fmt(levels!.buy_low, 2)} – ${fmt(levels!.buy_high, 2)}
              </strong>
              <span>
                距买点 {fmt(levels!.buy_discount_pct, 1)}% · 中枢 $
                {fmt(levels!.ideal_buy, 2)}
              </span>
            </div>
            <div className="forecast-level-cell sell">
              <small>参考卖点区间</small>
              <strong>
                ${fmt(levels!.sell_low, 2)} – ${fmt(levels!.sell_high, 2)}
              </strong>
              <span>
                空间 +{fmt(levels!.upside_pct, 1)}% / +
                {fmt(levels!.target_upside_pct, 1)}%
              </span>
            </div>
            <div className="forecast-level-cell stop">
              <small>防守止损 &amp; 赔率</small>
              <strong>${fmt(levels!.stop_loss, 2)}</strong>
              <span>
                回撤 {fmt(levels!.downside_pct, 1)}% · 赔率{" "}
                {fmt(levels!.risk_reward_ratio, 2)}:1
              </span>
            </div>
          </div>

          <div className="forecast-action-row">
            <div
              className="forecast-pos-tags"
              title={`买点盈亏比 ${fmt(levels!.entry_risk_reward_ratio, 2)}:1`}
            >
              <span className="source-pill">{levels!.position_label}</span>
              <span className="muted-tag">置信度 {rating!.confidence}</span>
              {guardrailCount > 0 && (
                <button
                  type="button"
                  className="guardrail-pill-btn"
                  onClick={() => setDetailsOpen((v) => !v)}
                  title={rating!.guardrails.join("；")}
                >
                  <TriangleAlert size={12} />
                  <span>风控警示 {guardrailCount}</span>
                </button>
              )}
            </div>
            {levels!.stop_loss != null && levels!.sell_low != null && (
              <button
                type="button"
                className="button secondary forecast-apply-btn"
                onClick={() =>
                  onApplyForecastLevels(levels!.stop_loss!, levels!.sell_low!)
                }
                title="将参考止损与参考卖点预填到个人计划价"
              >
                采纳计划价
              </button>
            )}
          </div>

          <details
            className="insp-sub-details"
            open={detailsOpen}
            onToggle={(e) => setDetailsOpen(e.currentTarget.open)}
          >
            <summary>
              <span>
                {detailsOpen
                  ? "收起评分拆解、点位依据与警示"
                  : "点位依据、评分拆解与风控说明"}
              </span>
              <ChevronDown size={14} />
            </summary>

            <div className="insp-sub-body">
              {guardrailCount > 0 && (
                <div className="forecast-guardrails">
                  {rating!.guardrails.map((g, i) => (
                    <div key={i}>
                      <TriangleAlert size={14} />
                      <span>{g}</span>
                    </div>
                  ))}
                </div>
              )}

              <div className="forecast-anchors">
                <div>
                  <b>买入支撑：</b>
                  <span>{levels!.buy_anchors.join(" · ")}</span>
                </div>
                <div>
                  <b>卖出压力：</b>
                  <span>{levels!.sell_anchors.join(" · ")}</span>
                </div>
                <div>
                  <b>防守依据：</b>
                  <span>{levels!.stop_anchor}</span>
                </div>
              </div>

              <div className="rating-factors">
                {rating!.factors.map((f) => (
                  <div className="rating-factor-row" key={f.key}>
                    <div className="rf-head">
                      <span>{f.label}</span>
                      <em>{fmt(f.weight * 100, 0)}%</em>
                      <b>{f.score != null ? `${fmt(f.score, 1)}分` : "暂缺"}</b>
                    </div>
                    <small>{f.detail}</small>
                  </div>
                ))}
              </div>

              <p className="forecast-disclaimer">{rating!.disclaimer}</p>
            </div>
          </details>
        </>
      )}
    </section>
  );
}

/** 日线结构评分独立模块：一级展示总分与三维进度条，二级收纳注脚与原始技术指标 */
function DailyScoreCard({
  activeSummary,
  dimensionNotes,
  isLiveEvalView,
}: {
  activeSummary: Summary | null;
  dimensionNotes: Record<string, string>;
  isLiveEvalView: boolean;
}) {
  return (
    <section className="insp-card">
      <div className="insp-card-head">
        <h3>日线结构评分</h3>
        <span className="muted-tag">
          {isLiveEvalView
            ? "实时试算 · 未收盘"
            : activeSummary?.as_of
              ? time(activeSummary.as_of, "America/New_York").slice(0, 10)
              : "待更新"}
        </span>
      </div>
      <div className="insp-score-row">
        <div
          className={`insp-score-big ${scoreTone(activeSummary?.score, activeSummary?.state)}`}
        >
          {fmt(activeSummary?.score, 1)}
          <small>/100</small>
        </div>
        <span
          className={`state-badge ${scoreTone(activeSummary?.score, activeSummary?.state)}`}
        >
          {labels[activeSummary?.state ?? "unavailable"]}
        </span>
      </div>

      <div className="dim-list">
        {Object.entries(dimensionNames).map(([key, label]) => {
          const val = activeSummary?.dimensions?.[key];
          const contrib = activeSummary?.contributions?.[key];
          const delta = activeSummary?.contribution_changes?.[key];
          const weight = activeSummary?.weights?.[key];
          const note =
            dimensionNotes[key] ??
            activeSummary?.evidence?.[
              Object.keys(dimensionNames).indexOf(key)
            ] ??
            "暂无有效比较";
          return (
            <div className="dim-item" key={key} title={note}>
              <div className="dim-top">
                <span className="dim-label">
                  <i style={{ background: dimensionColors[key] }} />
                  {label}
                </span>
                <span className="dim-vals">
                  <b>{fmt(val, 1)}</b>
                  <small>
                    {weight != null
                      ? `×${fmt(weight * 100, 0)}% = ${fmt(contrib, 1)}`
                      : ""}
                    {delta != null
                      ? ` (${delta >= 0 ? "+" : ""}${fmt(delta, 1)})`
                      : ""}
                  </small>
                </span>
              </div>
              <div className="dim-bar">
                <i
                  style={{
                    width: `${Math.max(0, Math.min(100, val ?? 0))}%`,
                    background: dimensionColors[key],
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <details className="raw-indicators">
        <summary>
          <span>展开维度解读与原始技术指标</span>
          <ChevronDown size={15} />
        </summary>
        <div className="dim-notes-drawer">
          {Object.entries(dimensionNames).map(([key, label]) => {
            const note =
              dimensionNotes[key] ??
              activeSummary?.evidence?.[
                Object.keys(dimensionNames).indexOf(key)
              ] ??
              "暂无有效比较";
            return (
              <p key={key}>
                <b>{label}：</b>
                {note}
              </p>
            );
          })}
        </div>
        <dl>
          {[
            [
              "RSI14",
              "rsi",
              2,
              "14日相对强弱指标（0–100）：> 70 超买防追高，< 30 超卖留意企稳，50 为多空分界",
            ],
            [
              "ATR14",
              "atr",
              2,
              "14日平均真实波幅（美元）：衡量该股日常正常波动幅度，用于测算合理止损与买卖区间",
            ],
            [
              "相对量能 RVOL",
              "rvol",
              2,
              "当日成交量 ÷ 近20日均量：> 1.5 为显著放量，< 0.7 为明显缩量",
            ],
            [
              "20日 Z-score",
              "zscore20",
              2,
              "收盘价偏离20日均线的标准差倍数：> +2 短期偏热，< -2 短期超跌偏离",
            ],
            [
              "20日时序排名",
              "rank20",
              2,
              "收盘价在近20个交易日中的相对百分位（0–1）：越接近 1 越靠近20日高点",
            ],
            [
              "20日量价相关",
              "corr20",
              2,
              "近20日涨跌幅与成交量变化的相关系数（-1 到 +1）：正值代表放量上涨、缩量回调的健康量价配合",
            ],
          ].map(([label, key, digits, tip]) => (
            <div key={String(key)} title={String(tip)}>
              <dt>{label}</dt>
              <dd>
                {fmt(
                  activeSummary?.indicators?.[String(key)],
                  Number(digits),
                )}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </section>
  );
}

/** 估值与资产特征独立模块：个股自动展示估值与美债对照，ETF 自动展示基金与指数特征 */
function ValuationOrFundCard({ stock }: { stock: Stock }) {
  if (stock.instrument?.is_fund) {
    return (
      <section className="insp-card fund-profile-card">
        <div className="insp-card-head">
          <h3>基金与指数特征</h3>
          <span
            className={`verdict-chip tone-${
              stock.instrument.is_leveraged ? "warning" : "neutral"
            }`}
          >
            {stock.instrument.type_label}
          </span>
        </div>
        {stock.instrument.benchmark && (
          <p className="fund-benchmark">{stock.instrument.benchmark}</p>
        )}
        <div className="val-grid">
          <div
            className="val-cell"
            title={
              stock.fund_metrics?.high_52w != null &&
              stock.fund_metrics?.low_52w != null
                ? `近${stock.fund_metrics.window_days}日区间：$${fmt(stock.fund_metrics.low_52w, 2)} – $${fmt(stock.fund_metrics.high_52w, 2)}`
                : "最新收盘距近1年（252交易日）高点的回撤幅度"
            }
          >
            <small>距52周高点回撤</small>
            <strong
              className={
                stock.fund_metrics?.drawdown_from_high_pct == null
                  ? ""
                  : stock.fund_metrics.drawdown_from_high_pct <= -20
                    ? "amber-text"
                    : "positive"
              }
            >
              {fmt(stock.fund_metrics?.drawdown_from_high_pct, 1)}
              <em>%</em>
            </strong>
          </div>
          <div
            className="val-cell"
            title="0% 为近1年最低点，100% 为近1年最高点，衡量当前所处价格分位"
          >
            <small>近1年价格分位</small>
            <strong>
              {fmt(stock.fund_metrics?.range_position_pct, 0)}
              <em>%</em>
            </strong>
          </div>
          <div
            className="val-cell"
            title={
              stock.fund_metrics?.hv20_pct != null
                ? `近20日年化波动率 ${fmt(stock.fund_metrics.hv20_pct, 1)}%`
                : "近60个交易日收益率年化波动率，数值越高波动与杠杆损耗越大"
            }
          >
            <small>60日年化波动率</small>
            <strong
              className={
                stock.fund_metrics?.hv60_pct != null &&
                stock.fund_metrics.hv60_pct >= 50
                  ? "amber-text"
                  : ""
              }
            >
              {fmt(stock.fund_metrics?.hv60_pct, 1)}
              <em>%</em>
            </strong>
          </div>
          <div
            className="val-cell"
            title={
              stock.fund_metrics?.return_60d_pct != null
                ? `近20日 ${fmt(stock.fund_metrics.return_20d_pct, 1)}% · 近60日 ${fmt(stock.fund_metrics.return_60d_pct, 1)}%`
                : "近1年窗口内从阶段高点到低点的最大回撤幅度"
            }
          >
            <small>近1年最大回撤</small>
            <strong>
              {fmt(stock.fund_metrics?.max_drawdown_pct, 1)}
              <em>%</em>
            </strong>
          </div>
        </div>
        {stock.instrument.is_leveraged && stock.instrument.risk_notice && (
          <div className="fund-risk-banner">
            <TriangleAlert size={14} />
            <span>{stock.instrument.risk_notice}</span>
          </div>
        )}
        <p className="val-footnote">
          {stock.research?.valuation?.dividend_yield_pct != null
            ? `派息率 TTM ${fmt(stock.research.valuation.dividend_yield_pct, 2)}%`
            : "派息率暂无"}
          {stock.fund_metrics?.ma200_gap_pct != null
            ? ` · 相对年线 ${stock.fund_metrics.ma200_gap_pct >= 0 ? "+" : ""}${fmt(stock.fund_metrics.ma200_gap_pct, 1)}%`
            : ""}
          。
          {stock.instrument.is_leveraged
            ? "杠杆/反向基金派息多含现金利息或结构分配，不按公司盈利评估。"
            : "指数/行业/商品基金不采用易失真的基金主体 PE/PB 口径。"}
        </p>
      </section>
    );
  }

  return (
    <section className="insp-card">
      <div className="insp-card-head">
        <h3>估值与美债对照</h3>
        <span
          className={`fresh-tag ${stock.research?.valuation?.fresh ? "ok" : "stale"}`}
        >
          {stock.research?.valuation?.source ?? "券商"} ·{" "}
          {stock.research?.valuation?.fresh ? "有效" : "待更新"}
        </span>
      </div>
      <div className="val-grid">
        <div className="val-cell">
          <small>滚动市盈率 PE</small>
          <strong>
            {fmt(stock.research?.valuation?.pe_ttm, 1)}
            <em>倍</em>
          </strong>
        </div>
        <div className="val-cell">
          <small>市净率 PB</small>
          <strong>
            {fmt(stock.research?.valuation?.pb, 2)}
            <em>倍</em>
          </strong>
        </div>
        <div className="val-cell">
          <small>股息率 TTM</small>
          <strong>
            {fmt(stock.research?.valuation?.dividend_yield_pct, 2)}
            <em>%</em>
          </strong>
        </div>
        <div className="val-cell">
          <small>盈利收益率 − 10Y美债</small>
          <strong
            className={
              stock.research?.yield_gap_pp == null
                ? ""
                : stock.research.yield_gap_pp >= 0
                  ? "positive"
                  : "amber-text"
            }
          >
            {stock.research?.yield_gap_pp != null &&
            stock.research.yield_gap_pp >= 0
              ? "+"
              : ""}
            {fmt(stock.research?.yield_gap_pp, 2)}
            <em>pp</em>
          </strong>
        </div>
      </div>
      <p className="val-footnote">
        盈利收益率 {fmt(stock.research?.earnings_yield_pct, 2)}%
        {stock.research?.real_yield_gap_pp != null &&
        stock.research?.real_ten_year != null
          ? ` · 实际利率利差（减 10Y TIPS ${fmt(stock.research.real_ten_year, 2)}%）${stock.research.real_yield_gap_pp >= 0 ? "+" : ""}${fmt(stock.research.real_yield_gap_pp, 2)}pp`
          : ""}
        （取数 {time(stock.research?.valuation?.fetched_at)}
        ）。名义与实际利差仅作收益率水平参照，非预期回报。
      </p>
    </section>
  );
}

/** 独立风险检查模块 */
function RiskCheckCard({ activeSummary }: { activeSummary: Summary | null }) {
  return (
    <section className="insp-card">
      <div className="insp-card-head">
        <h3>
          <ShieldCheck size={15} />
          独立风险检查
        </h3>
      </div>
      <div className="risk-list">
        {activeSummary?.risks?.length ? (
          activeSummary.risks.map((r) => (
            <div className="risk-item warn" key={r}>
              <TriangleAlert size={15} />
              <span>{r}</span>
            </div>
          ))
        ) : (
          <div className="risk-item ok">
            <Check size={15} />
            <span>
              {activeSummary?.valid
                ? "当前规则未标记额外技术风险"
                : "基础日线或指标数据待补齐"}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}

/** 右侧研判模块的自定义显隐与拖拽/按钮排序面板 */
function InspectorModuleManager({
  layout,
  hasExtendedHours,
  onToggle,
  onMove,
  onReorder,
  onReset,
  onClose,
}: {
  layout: InspectorLayoutConfig;
  hasExtendedHours: boolean;
  onToggle: (id: InspectorModuleId) => void;
  onMove: (id: InspectorModuleId, delta: -1 | 1) => void;
  onReorder: (fromId: InspectorModuleId, toId: InspectorModuleId) => void;
  onReset: () => void;
  onClose: () => void;
}) {
  const [draggingId, setDraggingId] = useState<InspectorModuleId | null>(null);
  const [dragOverId, setDragOverId] = useState<InspectorModuleId | null>(null);

  const isDefault =
    layout.hidden.length === 0 &&
    layout.order.every((id, idx) => id === DEFAULT_INSPECTOR_ORDER[idx]);

  return (
    <section
      className="insp-card module-mgr-card"
      aria-label="自定义右侧模块顺序与显示"
    >
      <div className="mod-mgr-head">
        <div>
          <h3>自定义右侧模块</h3>
          <small>拖拽手柄或点箭头调序，开关控制显示</small>
        </div>
        <button
          type="button"
          className="legend-close-btn"
          onClick={onClose}
          aria-label="收起模块自定义面板"
        >
          <X size={15} />
        </button>
      </div>

      <div className="mod-mgr-list" role="list">
        {layout.order.map((id, idx) => {
          const meta = INSPECTOR_MODULE_MAP[id];
          if (!meta) return null;
          const visible = !layout.hidden.includes(id);
          const isDragging = draggingId === id;
          const isDragOver = dragOverId === id && draggingId !== id;
          return (
            <div
              key={id}
              role="listitem"
              data-config-module-id={id}
              draggable
              className={`mod-mgr-row ${visible ? "" : "is-hidden"} ${
                isDragging ? "dragging" : ""
              } ${isDragOver ? "drag-over" : ""}`}
              onDragStart={(e) => {
                setDraggingId(id);
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", id);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                if (dragOverId !== id) setDragOverId(id);
              }}
              onDragLeave={() => {
                if (dragOverId === id) setDragOverId(null);
              }}
              onDrop={(e) => {
                e.preventDefault();
                const fromId =
                  draggingId ||
                  (e.dataTransfer.getData("text/plain") as InspectorModuleId);
                if (fromId && fromId !== id) {
                  onReorder(fromId, id);
                }
                setDraggingId(null);
                setDragOverId(null);
              }}
              onDragEnd={() => {
                setDraggingId(null);
                setDragOverId(null);
              }}
            >
              <span
                className="mod-mgr-grip"
                title="按住拖拽调整模块顺序"
                aria-hidden="true"
              >
                <GripVertical size={14} />
              </span>

              <button
                type="button"
                role="switch"
                aria-checked={visible}
                aria-label={`${visible ? "隐藏" : "显示"} ${meta.title}`}
                className={`mod-switch ${visible ? "on" : ""}`}
                onClick={() => onToggle(id)}
              >
                <span className="mod-switch-thumb" />
              </button>

              <div className="mod-mgr-info" title={meta.desc}>
                <span className="mod-mgr-title">
                  {meta.title}
                  {id === "extended_hours" && !hasExtendedHours && (
                    <em>当前无数据</em>
                  )}
                </span>
                <small>{meta.desc}</small>
              </div>

              <div className="mod-mgr-order-btns">
                <button
                  type="button"
                  className="mod-order-btn"
                  disabled={idx === 0}
                  onClick={() => onMove(id, -1)}
                  aria-label={`上移 ${meta.title}`}
                  title="上移一位"
                >
                  <ArrowUp size={13} />
                </button>
                <button
                  type="button"
                  className="mod-order-btn"
                  disabled={idx === layout.order.length - 1}
                  onClick={() => onMove(id, 1)}
                  aria-label={`下移 ${meta.title}`}
                  title="下移一位"
                >
                  <ArrowDown size={13} />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mod-mgr-foot">
        <button
          type="button"
          className="text-btn"
          disabled={isDefault}
          onClick={onReset}
        >
          <RotateCcw size={13} />
          恢复默认
        </button>
        <button
          type="button"
          className="button secondary mod-mgr-done-btn"
          onClick={onClose}
        >
          完成
        </button>
      </div>
    </section>
  );
}

export default function StockInspector({
  tab,
  onTabChange,
  stock,
  summary,
  evalMode = "confirmed",
  liveEval = null,
  liveEvalBusy = false,
  onEvalModeChange,
  onRefreshLiveEval,
  analysis,
  events,
  channels,
  mode,
  status,
  cooldownMinutes,
  onEditPlan,
  onApplyForecastLevels,
  onAnalyze,
  onPreview,
  onSelectSymbol,
  onOpenDeliveries,
  onOpenSettings,
}: {
  tab: InspectorTab;
  onTabChange: (t: InspectorTab) => void;
  stock: Stock | null;
  summary: Summary | null;
  evalMode?: EvalMode;
  liveEval?: LiveEvaluation | null;
  liveEvalBusy?: boolean;
  onEvalModeChange?: (mode: EvalMode) => void;
  onRefreshLiveEval?: () => void;
  analysis: Analysis | undefined;
  events: Signal[];
  channels: Dashboard["channels"] | undefined;
  mode: string;
  status: string;
  cooldownMinutes: number;
  onEditPlan: () => void;
  onApplyForecastLevels: (stopLoss: number, sellLow: number) => void;
  onAnalyze: () => void;
  onPreview: () => void;
  onSelectSymbol: (symbol: string) => void;
  onOpenDeliveries: () => void;
  onOpenSettings: () => void;
}) {
  const [eventFilter, setEventFilter] = useState<"all" | "current" | "risk">(
    "all",
  );
  const [managerOpen, setManagerOpen] = useState(false);
  const {
    layout,
    toggle: toggleModule,
    move: moveModule,
    reorder: reorderModule,
    reset: resetModules,
    showAll: showAllModules,
  } = useInspectorLayout();

  const visibleEvents = events.filter((e) => {
    if (eventFilter === "current" && stock) return e.symbol === stock.symbol;
    if (eventFilter === "risk") return e.severity !== "info";
    return true;
  });

  const activeSummary = summary ?? stock?.primary ?? null;
  const dimensionNotes = stock?.verdict?.dimension_notes ?? {};
  const codexStatus = channels?.codex;
  const codexBusy =
    analysis?.status === "running" || analysis?.status === "queued";
  const hasLiveEval = Boolean(liveEval?.available);
  const isLiveEvalView = evalMode === "live" && hasLiveEval;
  const liveScoreDelta = liveEval?.score_delta;
  const liveRatingLabel = liveEval?.forecast?.rating?.label ?? "";

  const hasExtendedHours = Boolean(
    stock?.extended_hours?.available && stock?.extended_hours?.price != null,
  );
  const hiddenSet = useMemo(() => new Set(layout.hidden), [layout.hidden]);
  const enabledCount = layout.order.length - layout.hidden.length;

  const liveEvalBtnTitle = (() => {
    if (!hasLiveEval || !liveEval) {
      return liveEval?.reason || "当前暂无更新的未收盘行情可试算";
    }
    const parts = [`按最新价 $${fmt(liveEval.price, 2)} 临时试算指标、买卖点与波浪`];
    if (liveScoreDelta != null) {
      parts.push(
        `日线分 ${liveScoreDelta >= 0 ? "+" : ""}${fmt(liveScoreDelta, 1)}`,
      );
    }
    if (
      liveEval.rating_changed &&
      liveEval.prev_rating_label &&
      liveRatingLabel
    ) {
      parts.push(`${liveEval.prev_rating_label}→${liveRatingLabel}`);
    }
    return parts.join(" · ");
  })();

  const renderModule = (id: InspectorModuleId): ReactNode => {
    if (!stock) return null;
    switch (id) {
      case "forecast":
        return (
          <ForecastCard
            stock={stock}
            onApplyForecastLevels={onApplyForecastLevels}
          />
        );
      case "wave_trend":
        return <WaveTrendCard stock={stock} />;
      case "extended_hours":
        return hasExtendedHours ? <ExtendedHoursCard stock={stock} /> : null;
      case "plan_range":
        return <PlanRangeBar stock={stock} onEditPlan={onEditPlan} />;
      case "daily_score":
        return (
          <DailyScoreCard
            activeSummary={activeSummary}
            dimensionNotes={dimensionNotes}
            isLiveEvalView={isLiveEvalView}
          />
        );
      case "valuation_profile":
        return <ValuationOrFundCard stock={stock} />;
      case "risk_check":
        return <RiskCheckCard activeSummary={activeSummary} />;
    }
  };

  return (
    <aside className="inspector-panel" aria-label="个股研判与工具">
      <div className="inspector-tabs" role="tablist" aria-label="研判功能区">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "summary"}
          className={tab === "summary" ? "active" : ""}
          onClick={() => onTabChange("summary")}
        >
          <Gauge size={15} />
          综合研判
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "codex"}
          className={tab === "codex" ? "active" : ""}
          onClick={() => onTabChange("codex")}
        >
          <Bot size={15} />
          Codex 总结
          {codexBusy && <LoaderCircle size={13} className="spin" />}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "events"}
          className={tab === "events" ? "active" : ""}
          onClick={() => onTabChange("events")}
        >
          <Bell size={15} />
          提醒动态
          {events.length > 0 && <em>{events.length}</em>}
        </button>
      </div>

      <div className="inspector-body">
        {tab === "summary" && stock && (
          <>
            {/* 顶部超紧凑控制栏：左置双口径切换，右置模块显示与排序入口 */}
            <div className="inspector-ctrl-bar" aria-label="研判口径与模块布局">
              {mode === "live" && onEvalModeChange ? (
                <div className="inspector-ctrl-left">
                  <div
                    className="eval-mode-seg compact"
                    role="group"
                    aria-label="指标评估口径"
                  >
                    <button
                      type="button"
                      className={!isLiveEvalView ? "active" : ""}
                      onClick={() => onEvalModeChange("confirmed")}
                      title="以最近已确认的纽约收盘前复权日线计算（长期复核与告警基准）"
                    >
                      收盘确认
                    </button>
                    <button
                      type="button"
                      className={isLiveEvalView ? "live-active" : ""}
                      disabled={!hasLiveEval}
                      onClick={() => onEvalModeChange("live")}
                      title={liveEvalBtnTitle}
                    >
                      {hasLiveEval && <span className="eval-live-dot" />}
                      最新试算
                    </button>
                  </div>
                  {isLiveEvalView && onRefreshLiveEval && (
                    <button
                      type="button"
                      className="eval-refresh-btn icon-only"
                      disabled={liveEvalBusy}
                      onClick={onRefreshLiveEval}
                      aria-label="按最新报价重新试算"
                      title="按当前最新报价立即重新试算"
                    >
                      <RefreshCw
                        size={13}
                        className={liveEvalBusy ? "spin" : ""}
                      />
                    </button>
                  )}
                </div>
              ) : (
                <span className="inspector-ctrl-label">
                  研判模块 {enabledCount}/{layout.order.length}
                </span>
              )}

              <button
                type="button"
                className={`module-mgr-btn ${managerOpen ? "active" : ""}`}
                onClick={() => setManagerOpen((v) => !v)}
                aria-expanded={managerOpen}
                aria-label="自定义右侧模块显示与顺序"
                title="自定义右侧各功能模块是否显示及上下顺序"
              >
                <SlidersHorizontal size={13} />
                <span>模块</span>
                {layout.hidden.length > 0 && (
                  <em className="mod-count-pill">
                    {enabledCount}/{layout.order.length}
                  </em>
                )}
              </button>
            </div>

            {isLiveEvalView && liveEval && (
              <div
                className="eval-mode-banner"
                title={
                  liveEval.disclaimer ||
                  "未收盘临时预览，仅作盘中决策参考；正式复核与告警仍按收盘确认日线执行。"
                }
              >
                <div className="eval-mode-banner-head">
                  <span>
                    {liveEval.basis_label || "盘中试算"} · $
                    {fmt(liveEval.price, 2)}
                    {liveEval.change_pct != null
                      ? ` (${liveEval.change_pct >= 0 ? "+" : ""}${fmt(liveEval.change_pct, 1)}%)`
                      : ""}
                  </span>
                  {liveScoreDelta != null && (
                    <span className="eval-mode-delta">
                      评分 {liveScoreDelta >= 0 ? "+" : ""}
                      {fmt(liveScoreDelta, 1)}
                    </span>
                  )}
                  {liveEval.rating_changed &&
                    liveEval.prev_rating_label &&
                    liveRatingLabel && (
                      <span className="eval-mode-delta">
                        {liveEval.prev_rating_label}→{liveRatingLabel}
                      </span>
                    )}
                </div>
              </div>
            )}

            {managerOpen && (
              <InspectorModuleManager
                layout={layout}
                hasExtendedHours={hasExtendedHours}
                onToggle={toggleModule}
                onMove={moveModule}
                onReorder={reorderModule}
                onReset={resetModules}
                onClose={() => setManagerOpen(false)}
              />
            )}

            {enabledCount === 0 ? (
              <section className="insp-card inspector-empty-modules">
                <b>已隐藏全部研判模块</b>
                <p>可在上方「模块」面板重新勾选需要展示的功能模块。</p>
                <button
                  type="button"
                  className="button secondary"
                  onClick={showAllModules}
                >
                  全部显示
                </button>
              </section>
            ) : (
              layout.order.map((moduleId) => {
                if (hiddenSet.has(moduleId)) return null;
                const node = renderModule(moduleId);
                if (!node) return null;
                return (
                  <div
                    key={moduleId}
                    className="insp-module-slot"
                    data-module-id={moduleId}
                  >
                    {node}
                  </div>
                );
              })
            )}
          </>
        )}

        {tab === "codex" && (
          <div className="codex-tab">
            <section className="insp-card">
              <div className="insp-card-head">
                <h3>Codex 长期复核总结</h3>
                <span className="manual-pill">手动触发模式</span>
              </div>
              <p className="codex-desc">
                已关闭后台自动调用，仅在您手动点击下方按钮时，使用当前已确认日线、估值、美债利率与脱敏计划距离生成总结。
              </p>
              <div className="codex-meta-row">
                <span>
                  模型：<b>{codexStatus?.model ?? "未检测到 Codex CLI"}</b>
                </span>
                <span>
                  状态：
                  <b
                    className={
                      codexStatus?.status === "ready" ? "positive" : ""
                    }
                  >
                    {codexStatus?.status === "running"
                      ? "运行中"
                      : codexStatus?.status === "ready"
                        ? "已就绪"
                        : codexStatus?.status ?? "不可用"}
                  </b>
                </span>
              </div>
              <div className="codex-actions">
                <button
                  type="button"
                  className="button primary codex-main-btn"
                  disabled={!stock || codexBusy}
                  onClick={onAnalyze}
                >
                  {codexBusy ? (
                    <LoaderCircle size={16} className="spin" />
                  ) : (
                    <Sparkles size={16} />
                  )}
                  {codexBusy
                    ? "正在生成总结…"
                    : analysis?.status === "completed"
                      ? "重新生成总结"
                      : "生成 Codex 总结"}
                </button>
                <button
                  type="button"
                  className="button secondary"
                  disabled={!stock}
                  onClick={onPreview}
                >
                  <Eye size={15} />
                  查看脱敏预览
                </button>
              </div>
            </section>

            {analysis?.status === "completed" && analysis.result ? (
              <section className="insp-card codex-result-card">
                <div className="codex-verdict-head">
                  <Sparkles size={17} />
                  <strong>{labels[analysis.result.action] ?? analysis.result.action}</strong>
                  <span>
                    依据 {time(analysis.result.data_as_of, "America/New_York")}
                  </span>
                </div>
                <p className="codex-conclusion">{analysis.result.conclusion}</p>

                <div className="codex-block">
                  <h4>核心依据</h4>
                  <ul>
                    {(analysis.result.evidence ?? []).map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>

                <div className="codex-block">
                  <h4>主要风险与局限</h4>
                  <ul>
                    {(analysis.result.risks ?? []).map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>

                <div className="codex-block">
                  <h4>改变计划的条件</h4>
                  <ul>
                    {(analysis.result.confirmation_conditions ?? []).map(
                      (item, idx) => (
                        <li key={idx}>{item}</li>
                      ),
                    )}
                  </ul>
                </div>
              </section>
            ) : (
              <section className="insp-card codex-empty-card">
                <Bot size={26} />
                <b>
                  {analysis?.status === "running"
                    ? `正在复核 ${ticker(stock?.symbol ?? "")} 的长期计划…`
                    : analysis?.status === "queued"
                      ? "分析任务已排队，等待执行…"
                      : analysis?.status === "failed"
                        ? "上一次分析未完成"
                        : "尚未生成 Codex 总结"}
                </b>
                <p>
                  {analysis?.error ??
                    "点击上方「生成 Codex 总结」按钮即可针对当前股票形成独立复核意见。"}
                </p>
              </section>
            )}

            <div className="privacy-strip">
              <LockKeyhole size={14} />
              <span>
                仅发送脱敏快照，不发送账户标识、股数、实际金额、成本和成交流水。
              </span>
            </div>
          </div>
        )}

        {tab === "events" && (
          <div className="events-tab">
            <div className="event-filter-row">
              {(
                [
                  ["all", "全部提醒"],
                  ["current", "当前股票"],
                  ["risk", "仅风险"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={eventFilter === id ? "active" : ""}
                  onClick={() => setEventFilter(id)}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="events-list">
              {visibleEvents.slice(0, 20).map((e) => (
                <button
                  type="button"
                  key={e.id}
                  className={`event-item ${e.severity}`}
                  onClick={() => {
                    if (e.symbol !== "PORTFOLIO") onSelectSymbol(e.symbol);
                  }}
                >
                  <span className="event-ico">
                    {e.severity === "critical" ? (
                      <TriangleAlert size={15} />
                    ) : e.kind.includes("weak") ? (
                      <ArrowDownRight size={15} />
                    ) : (
                      <ArrowUpRight size={15} />
                    )}
                  </span>
                  <div className="event-body">
                    <div className="event-top">
                      <b>{e.symbol === "PORTFOLIO" ? "组合摘要" : ticker(e.symbol)}</b>
                      <small>{time(e.data_as_of)}</small>
                    </div>
                    <strong>{e.title}</strong>
                    <p>{e.message}</p>
                    <div className="event-meta">
                      <span>{labels[e.timeframe] ?? e.timeframe}</span>
                      {e.score != null && <span>评分 {fmt(e.score, 0)}</span>}
                      {e.historical && <em>历史回放</em>}
                    </div>
                  </div>
                </button>
              ))}
              {!visibleEvents.length && (
                <div className="events-empty">
                  <Bell size={24} />
                  <b>暂无符合条件的提醒</b>
                  <p>
                    只有日线结构变化或触及预设关键价时才会生成记录，同类提醒冷却{" "}
                    {cooldownMinutes} 分钟。
                  </p>
                </div>
              )}
            </div>

            <section className="insp-card channels-card">
              <div className="insp-card-head">
                <h3>
                  <CircleDot size={14} />
                  接入与通道状态
                </h3>
                <button
                  type="button"
                  className="text-btn"
                  onClick={onOpenDeliveries}
                >
                  投递记录
                </button>
              </div>
              {[
                [
                  "LongPort 行情",
                  mode === "live" ? status : "demo",
                  mode === "live" ? "只读行情与自选同步" : "合成演示数据",
                ],
                [
                  "Codex CLI",
                  channels?.codex?.status ?? "unavailable",
                  channels?.codex?.model ?? "未检测到 CLI",
                ],
                [
                  "QQ 官方机器人",
                  channels?.qq?.status ?? "disabled",
                  channels?.qq?.detail ?? "未启用",
                ],
              ].map(([name, st, desc]) => (
                <div className="conn-row" key={String(name)}>
                  <span
                    className={`conn-dot ${["live", "ready", "delivered"].includes(String(st)) ? "ok" : st === "demo" ? "demo" : ""}`}
                  />
                  <div>
                    <b>{name}</b>
                    <small>{desc}</small>
                  </div>
                  <em>{st}</em>
                </div>
              ))}
              <button
                type="button"
                className="button secondary full-btn"
                onClick={onOpenSettings}
              >
                管理连接与规则设置
              </button>
            </section>
          </div>
        )}
      </div>
    </aside>
  );
}
