import {
  ArrowDownRight,
  ArrowUpRight,
  Bell,
  Bot,
  Check,
  ChevronDown,
  CircleDot,
  Eye,
  Gauge,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import {
  fmt,
  labels,
  ticker,
  time,
  type Analysis,
  type Dashboard,
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
  const stop = stock.long_plan.stop;
  const target = stock.long_plan.target;
  const close = stock.long_plan.close ?? stock.quote.last ?? null;
  const cost =
    stock.broker_quantity > 0 && stock.cost_price != null
      ? stock.cost_price
      : null;

  const stopDist = stock.long_plan.stop_distance_percent;
  const targetDist = stock.long_plan.target_distance_percent;

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

function ForecastCard({
  stock,
  onApplyForecastLevels,
}: {
  stock: Stock;
  onApplyForecastLevels: (stopLoss: number, sellLow: number) => void;
}) {
  const forecast = stock.forecast;
  const rating = forecast?.rating;
  const levels = forecast?.levels;
  const available = Boolean(
    forecast && levels?.available && rating?.available,
  );

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
          {rating?.disclaimer && (
            <p className="forecast-disclaimer">{rating.disclaimer}</p>
          )}
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
                采纳为计划价
              </button>
            )}
          </div>

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

          {rating!.guardrails.length > 0 && (
            <div className="forecast-guardrails">
              {rating!.guardrails.map((g, i) => (
                <div key={i}>
                  <TriangleAlert size={14} />
                  <span>{g}</span>
                </div>
              ))}
            </div>
          )}

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
        </>
      )}
    </section>
  );
}

export default function StockInspector({
  tab,
  onTabChange,
  stock,
  summary,
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
            <ForecastCard
              stock={stock}
              onApplyForecastLevels={onApplyForecastLevels}
            />

            <PlanRangeBar stock={stock} onEditPlan={onEditPlan} />

            <section className="insp-card">
              <div className="insp-card-head">
                <h3>日线结构评分</h3>
                <span className="muted-tag">
                  {activeSummary?.as_of
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
                    <div className="dim-item" key={key}>
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
                      <p className="dim-note">{note}</p>
                    </div>
                  );
                })}
              </div>

              <details className="raw-indicators">
                <summary>
                  <span>展开原始技术指标与算子</span>
                  <ChevronDown size={15} />
                </summary>
                <dl>
                  {[
                    ["RSI14", "rsi", 2],
                    ["ATR14", "atr", 2],
                    ["相对量能 RVOL", "rvol", 2],
                    ["20日 Z-score", "zscore20", 2],
                    ["20日时序排名", "rank20", 2],
                    ["20日量价相关", "corr20", 2],
                  ].map(([label, key, digits]) => (
                    <div key={String(key)}>
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

            <section className="insp-card">
              <div className="insp-card-head">
                <h3>估值与美债对照</h3>
                <span
                  className={`fresh-tag ${stock.research.valuation.fresh ? "ok" : "stale"}`}
                >
                  {stock.research.valuation.source} ·{" "}
                  {stock.research.valuation.fresh ? "有效" : "待更新"}
                </span>
              </div>
              <div className="val-grid">
                <div className="val-cell">
                  <small>滚动市盈率 PE</small>
                  <strong>
                    {fmt(stock.research.valuation.pe_ttm, 1)}
                    <em>倍</em>
                  </strong>
                </div>
                <div className="val-cell">
                  <small>市净率 PB</small>
                  <strong>
                    {fmt(stock.research.valuation.pb, 2)}
                    <em>倍</em>
                  </strong>
                </div>
                <div className="val-cell">
                  <small>股息率 TTM</small>
                  <strong>
                    {fmt(stock.research.valuation.dividend_yield_pct, 2)}
                    <em>%</em>
                  </strong>
                </div>
                <div className="val-cell">
                  <small>盈利收益率 − 10Y美债</small>
                  <strong
                    className={
                      stock.research.yield_gap_pp == null
                        ? ""
                        : stock.research.yield_gap_pp >= 0
                          ? "positive"
                          : "amber-text"
                    }
                  >
                    {stock.research.yield_gap_pp != null &&
                    stock.research.yield_gap_pp >= 0
                      ? "+"
                      : ""}
                    {fmt(stock.research.yield_gap_pp, 2)}
                    <em>pp</em>
                  </strong>
                </div>
              </div>
              <p className="val-footnote">
                盈利收益率 {fmt(stock.research.earnings_yield_pct, 2)}%（取数{" "}
                {time(stock.research.valuation.fetched_at)}）。利差仅作收益率水平参照。
              </p>
            </section>

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
                    {analysis.result.evidence.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>

                <div className="codex-block">
                  <h4>主要风险与局限</h4>
                  <ul>
                    {analysis.result.risks.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>

                <div className="codex-block">
                  <h4>改变计划的条件</h4>
                  <ul>
                    {analysis.result.confirmation_conditions.map(
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
