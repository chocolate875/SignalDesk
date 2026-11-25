import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { BookOpen, Check, ChevronRight, HelpCircle, X } from "lucide-react";
import { fmt, ticker, type Stock, type WavePivot, type WaveTrend } from "./types";

const STRUCTURE_CN: Record<string, string> = {
  HH: "高点抬高",
  HL: "低点抬高",
  LH: "高点降低",
  LL: "低点降低",
  H: "阶段高点",
  L: "阶段低点",
};

type ModalTab = "current" | "waves" | "fib";

/** 将波浪拐点格式化为通俗中文名称 */
function pivotTitle(p: WavePivot): string {
  if (p.wave_label) {
    if (p.wave_label === "0") return "波浪起点";
    if (!p.confirmed) return `第${p.wave_label}浪`;
    const kindWord = p.kind === "H" ? "高点" : "低点";
    return `第${p.wave_label}浪${kindWord}`;
  }
  return STRUCTURE_CN[p.structure] ?? (p.kind === "H" ? "波段高点" : "波段低点");
}

/** 计算价位相对当前收盘的百分比距离 */
function pctDiff(target: number | null | undefined, base: number | null | undefined): string {
  if (target == null || base == null || !Number.isFinite(target) || !Number.isFinite(base) || base <= 0) {
    return "";
  }
  const pct = (target / base - 1) * 100;
  return `${pct >= 0 ? "+" : ""}${fmt(pct, 1)}%`;
}

/** 缩短 YYYY-MM-DD 为 MM-DD 保持紧凑 */
function shortDate(d: string): string {
  return d && d.length >= 10 ? d.slice(5) : d;
}

/** 二级说明窗口：透明展示当前参数实测值、波浪各点位含义与斐波那契交易纪律 */
function WaveTrendGuideModal({
  stock,
  wt,
  onClose,
}: {
  stock: Stock;
  wt: WaveTrend;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<ModalTab>("current");
  const trend = wt.trend;
  const wave = wt.wave;
  const ch = trend.channel;
  const isDown = trend.direction === "downtrend";
  const close = stock.long_plan?.close ?? stock.quote?.last ?? null;
  const forecastStop = stock.forecast?.levels?.stop_loss ?? null;
  const atr = stock.primary?.indicators?.atr ?? null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const posDesc = (() => {
    const p = trend.channel_position_pct;
    if (p == null) return "通道数据尚未就绪。";
    if (p < 0) return `当前为 ${fmt(p, 0)}%（< 0% 表示已跌破通道下轨，短线明显偏弱或超跌）。`;
    if (p <= 25) return `当前为 ${fmt(p, 0)}%（靠近 0% 下轨支撑区，上升趋势中常为低吸观察区）。`;
    if (p <= 75) return `当前为 ${fmt(p, 0)}%（处于 0%–100% 通道中段，节奏相对健康平稳）。`;
    if (p <= 100) return `当前为 ${fmt(p, 0)}%（靠近 100% 上轨压力区，短线偏热不宜盲目追高）。`;
    return `当前为 ${fmt(p, 0)}%（> 100% 表示已突破通道上轨，动能强势但短线偏离度加大）。`;
  })();

  const slopeDesc = (() => {
    const s = trend.slope_pct_per_20d;
    if (s == null) return "暂缺";
    const dir = s >= 2 ? "明显向上倾斜" : s <= -2 ? "明显向下倾斜" : "趋于走平震荡";
    return `每 20 个交易日通道中轨变化 ${s >= 0 ? "+" : ""}${fmt(s, 1)}%（${dir}）。`;
  })();

  const atrThresholdDesc =
    atr != null && close != null && close > 0
      ? `当前约 $${fmt(Math.max(2.8 * atr, 0.065 * close), 2)}（取 2.8×ATR14=$${fmt(2.8 * atr, 2)} 与 6.5%×收盘价=$${fmt(0.065 * close, 2)} 的较大值，中级波浪滤网）`
      : "取 2.8 × ATR14 与 6.5% × 收盘价的较大值（中级波浪滤网）";

  return createPortal(
    <div
      className="modal-shade"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        className="small-modal wt-modal"
        role="dialog"
        aria-modal="true"
        aria-label="波浪理论与趋势参数说明"
      >
        <header className="modal-header">
          <div>
            <h2>{ticker(stock.symbol)} · 波浪理论参数与点位说明</h2>
            <p className="wt-modal-sub">
              当前状态：{trend.label} · {wave.pattern_label}（{wave.current_wave} · 置信度{wave.confidence}
              {wave.degree_label ? ` · ${wave.degree_label}` : ""}）
            </p>
          </div>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="关闭波浪说明"
          >
            <X size={20} />
          </button>
        </header>

        <div className="wt-modal-tabs" role="tablist" aria-label="波浪说明分类">
          {(
            [
              ["current", "当前参数与校验"],
              ["waves", "波浪与点位怎么看"],
              ["fib", "斐波那契与纪律"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={tab === id}
              className={tab === id ? "active" : ""}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="wt-modal-body">
          {tab === "current" && (
            <>
              <div className="wt-param-grid">
                <div className="wt-param-card">
                  <div className="wt-param-head">
                    <b>趋势通道分位</b>
                    <em>
                      {trend.channel_position_pct != null
                        ? `${fmt(trend.channel_position_pct, 0)}%`
                        : "—"}
                    </em>
                  </div>
                  <p>
                    以 0% 为通道下轨、100% 为上轨衡量现价位置。{posDesc}
                  </p>
                </div>

                <div className="wt-param-card">
                  <div className="wt-param-head">
                    <b>20日通道斜率</b>
                    <em>
                      {trend.slope_pct_per_20d != null
                        ? `${trend.slope_pct_per_20d >= 0 ? "+" : ""}${fmt(trend.slope_pct_per_20d, 1)}%`
                        : "—"}
                    </em>
                  </div>
                  <p>
                    基于近 {ch?.window ?? 126} 个交易日收盘线性回归拟合。{slopeDesc}
                  </p>
                </div>

                <div className="wt-param-card">
                  <div className="wt-param-head">
                    <b>通道下 / 中 / 上轨</b>
                    <em>
                      {ch?.available
                        ? `$${fmt(ch.end_lower, 2)} / $${fmt(ch.end_mid, 2)} / $${fmt(ch.end_upper, 2)}`
                        : "—"}
                    </em>
                  </div>
                  <p>
                    图上三条平行虚线在最新交易日的精确坐标，带宽综合残差标准差与 ATR14 波动自适应确定。
                  </p>
                </div>

                <div className="wt-param-card">
                  <div className="wt-param-head">
                    <b>拐点确认反转阈值</b>
                    <em>严格因果</em>
                  </div>
                  <p>
                    {atrThresholdDesc}。仅当价格反向走完该幅度才锁定为已确认拐点；末尾带 <code>*</code> 与虚线表示当前波段仍在运行。
                  </p>
                </div>

                <div className="wt-param-card">
                  <div className="wt-param-head">
                    <b>道氏高低结构</b>
                    <em>{trend.structure}</em>
                  </div>
                  <p>
                    近期拐点顺序：
                    {trend.structure_code && trend.structure_code !== "待确认"
                      ? trend.structure_code
                          .split(" → ")
                          .map((c) => STRUCTURE_CN[c] ?? c)
                          .join(" → ")
                      : "待确认"}
                    。高点抬高 + 低点抬高为多头结构，高点降低 + 低点降低为空头结构。
                  </p>
                </div>

                <div className="wt-param-card">
                  <div className="wt-param-head">
                    <b>均线排列状态</b>
                    <em>{trend.label}</em>
                  </div>
                  <p>
                    {trend.ma_alignment}。系统综合道氏结构、MA20/50/200 排列与 20 日斜率三方投票判定主趋势方向。
                  </p>
                </div>
              </div>

              <div className="wt-rules-panel">
                <h4>艾略特波浪铁律校验（置信度：{wave.confidence}）</h4>
                {wave.rules_passed.length > 0 ? (
                  <ul className="wt-rules-ul">
                    {wave.rules_passed.map((r, i) => (
                      <li key={i}>
                        <Check size={14} />
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">
                    当前拐点数量尚少或未满足完整推动/三浪铁律，系统不强行标浪，仅以客观高低点与通道上下轨为准。
                  </p>
                )}
              </div>
            </>
          )}

          {tab === "waves" && (
            <>
              <div className="wt-explain-section">
                <h4>一、四个关键交易点位有什么区别？</h4>
                <div className="wt-compare-list">
                  <div className="wt-compare-item">
                    <b>
                      前高突破位
                      {trend.breakout_level != null && (
                        <em>${fmt(trend.breakout_level, 2)}</em>
                      )}
                    </b>
                    <p>
                      最近一个已确认的波段高点。放量有效站上该价位，说明买盘消化前高压力、多头趋势有望延续。
                    </p>
                  </div>
                  <div className="wt-compare-item">
                    <b>
                      {isDown ? "前高反转位" : "前低失效位"}
                      {trend.invalidation_level != null && (
                        <em>${fmt(trend.invalidation_level, 2)}</em>
                      )}
                    </b>
                    <p>
                      {isDown
                        ? "下降趋势中最近已确认的波段前高。只有收盘有效站上该价位，才代表空头「高点降低」结构被打破（趋势反转）。"
                        : "上升/震荡趋势中最近已确认的波段前低（如 2 浪或 4 浪低点）。收盘跌破该前低代表当前多头趋势结构失效。"}
                    </p>
                  </div>
                  <div className="wt-compare-item">
                    <b>
                      左侧「参考止损」（ATR 止损）
                      {forecastStop != null && <em>${fmt(forecastStop, 2)}</em>}
                    </b>
                    <p>
                      按近期 14 日平均波幅（ATR14）测算的<strong>单笔仓位止损参考</strong>；它与上面的「{isDown ? "前高反转位" : "前低失效位"}」衡量维度不同——前者管仓位回撤，后者看大趋势结构是否走坏。
                    </p>
                  </div>
                  <div className="wt-compare-item">
                    <b>波浪目标测算位（斐波那契）</b>
                    <p>
                      依据已确认的前浪幅度（如 1 浪长度 W1 或 A 浪长度），按 0.618 / 1.0 / 1.618 比例外推的潜在阻力或回调支撑参考位。
                    </p>
                  </div>
                </div>
              </div>

              <div className="wt-explain-section">
                <h4>二、图上每个波浪标号代表什么阶段？</h4>
                <div className="wt-wave-dict">
                  <div>
                    <b>起点（0）</b>
                    <span>本轮推动浪或调整浪的起涨 / 起跌锚点。</span>
                  </div>
                  <div>
                    <b>第 1 浪</b>
                    <span>新趋势初始启动段，方向刚拐头、市场分歧通常较大。</span>
                  </div>
                  <div>
                    <b>第 2 浪</b>
                    <span>首次回踩蓄势段（常见回撤 1 浪的 38.2%–61.8%），铁律是绝不跌破起点 0。</span>
                  </div>
                  <div>
                    <b>第 3 浪</b>
                    <span>主升 / 主跌爆发段，通常动能最强、成交配合度高，铁律是不可为最短推动浪。</span>
                  </div>
                  <div>
                    <b>第 4 浪</b>
                    <span>主升后的强势休整段，铁律是回踩不可跌入第 1 浪高点区间。</span>
                  </div>
                  <div>
                    <b>第 5 浪</b>
                    <span>推动末段冲刺，需留意通道上轨压力与动能背离，防范随后进入 A-B-C 回调。</span>
                  </div>
                  <div>
                    <b>A / B / C 浪</b>
                    <span>三浪逆势调整（主升中的回撤，或主跌中的弱反弹），C 浪常见与 A 浪等长。</span>
                  </div>
                  <div>
                    <b>带 * 号与虚线</b>
                    <span>代表当前这一浪仍在运行中，尚未出现反向超阈值拐点，后续随新收盘可能延伸。</span>
                  </div>
                </div>
              </div>
            </>
          )}

          {tab === "fib" && (
            <div className="wt-explain-section">
              <h4>斐波那契比例与顺势通道纪律</h4>
              <div className="wt-compare-list">
                <div className="wt-compare-item">
                  <b>0.618 黄金分割位</b>
                  <p>
                    常用于衡量第 2 浪回调支撑、空头反抽压力或第 5 浪保守目标（0.618 × 第 1 浪幅度）。
                  </p>
                </div>
                <div className="wt-compare-item">
                  <b>1.0 等长比例</b>
                  <p>
                    常用于测算 A-B-C 三浪调整的 C 浪等长支撑（C = 1.0 × A），或第 5 浪与第 1 浪等长目标。
                  </p>
                </div>
                <div className="wt-compare-item">
                  <b>1.618 主升扩展位</b>
                  <p>
                    第 3 浪主升（或主跌）最常见的动能延伸测算位（从 2 浪底向外延伸 1.618 × 第 1 浪幅度）。
                  </p>
                </div>
                <div className="wt-compare-item">
                  <b>趋势通道实战原则</b>
                  <p>
                    上升通道重在回踩下轨 / 中轨分批低吸、贴近上轨不追高；下降通道以防守观望为主，等有效站上前高反转再评估；箱体震荡看通道上下沿边界。波浪与通道仅作客观历史结构复核，不构成绝对涨跌预测或投资建议。
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        <footer className="modal-footer">
          <span>{wt.disclaimer || "严格因果计算 · 仅作历史结构复核参考"}</span>
          <button type="button" className="button primary" onClick={onClose}>
            知道了
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}

/** 右侧「波浪与趋势结构」一级简洁视图 + 二级说明弹窗入口 */
export default function WaveTrendCard({ stock }: { stock: Stock }) {
  const [guideOpen, setGuideOpen] = useState(false);
  const wt = stock.wave_trend;
  if (!wt) return null;

  const trend = wt.trend;
  const wave = wt.wave;
  const ch = trend.channel;
  const isDown = trend.direction === "downtrend";
  const close = stock.long_plan?.close ?? stock.quote?.last ?? null;

  // 提炼明确的波浪各节点（有标准浪号则展示完整浪序列，否则展示最近 4 个已识别波段拐点）
  const allPivots = wave.pivots ?? [];
  const taggedPivots = allPivots.filter((p) => Boolean(p.wave_label));
  const displayPivots =
    taggedPivots.length >= 2 ? taggedPivots : allPivots.slice(-4);
  const hasWaveTags = taggedPivots.length >= 2;

  const currentStageDesc =
    wave.current_wave && wave.current_wave !== "待确认"
      ? `${wave.pattern_label} · ${wave.current_wave}`
      : wave.pattern_label;

  return (
    <section className="insp-card wave-trend-card">
      <div className="insp-card-head">
        <div className="wt-head-left">
          <h3>波浪与趋势结构</h3>
          {wt.available && (
            <button
              type="button"
              className="wt-help-trigger"
              onClick={() => setGuideOpen(true)}
              title="打开波浪理论参数、铁律校验与各点位详细说明"
              aria-label="查看波浪理论参数与说明"
            >
              <HelpCircle size={13} />
              <span>说明</span>
            </button>
          )}
        </div>
        <span className={`verdict-chip tone-${trend.tone}`}>{trend.label}</span>
      </div>

      {!wt.available ? (
        <div className="forecast-unavail">
          <p>{wt.reason || wt.summary}</p>
        </div>
      ) : (
        <>
          {/* 1. 一句话直观定位：趋势方向 + 通道分位 */}
          <div className="wt-summary-box">
            <div className="wt-summary-top">
              <strong className={`tone-text-${wave.tone}`}>
                {currentStageDesc}
              </strong>
              <span className="wt-pos-chip">{trend.channel_position_label}</span>
            </div>
            <p className="wt-phase-note">{wave.phase_label}</p>
          </div>

          {/* 2. 核心客观趋势边界：突破位 / 失效反转位 / 回归平行通道 */}
          <div className="wt-points-block">
            <div className="wt-block-head">
              <b>结构边界与通道位置</b>
              <span>相对现价</span>
            </div>
            <div className="wt-key-grid">
              <div
                className="wt-key-card"
                title="最近已确认波段高点；放量突破代表多头趋势延续"
              >
                <small>前高突破位</small>
                <div className="wt-key-val">
                  <b>
                    {trend.breakout_level != null
                      ? `$${fmt(trend.breakout_level, 2)}`
                      : "—"}
                  </b>
                  {trend.breakout_level != null && close != null && (
                    <em>{pctDiff(trend.breakout_level, close)}</em>
                  )}
                </div>
              </div>
              <div
                className="wt-key-card"
                title={
                  isDown
                    ? "下降趋势最近前高；有效站上才代表空头反转"
                    : "上升/震荡趋势最近前低；收盘跌破代表趋势结构失效"
                }
              >
                <small>{isDown ? "前高反转位" : "前低失效位"}</small>
                <div className="wt-key-val">
                  <b className={isDown ? "accent-val" : "down"}>
                    {trend.invalidation_level != null
                      ? `$${fmt(trend.invalidation_level, 2)}`
                      : "—"}
                  </b>
                  {trend.invalidation_level != null && close != null && (
                    <em>{pctDiff(trend.invalidation_level, close)}</em>
                  )}
                </div>
              </div>
            </div>

            {ch?.available && (
              <div
                className="wt-channel-strip"
                title={`近 ${ch.window ?? 126} 日线性回归平行通道在最新收盘日的精确边界`}
              >
                <span>通道参考</span>
                <b>
                  下 ${fmt(ch.end_lower, 2)} · 中 ${fmt(ch.end_mid, 2)} · 上 $
                  {fmt(ch.end_upper, 2)}
                </b>
              </div>
            )}
          </div>

          {/* 3. 一句大白话行动参考 */}
          <div className="wt-guide">{wt.action_guide}</div>

          {/* 4. 二级折叠区：主观波浪计数点位与斐波那契测算（辅助参考，不主驱动评级） */}
          {(displayPivots.length > 0 || wave.fib_targets.length > 0) && (
            <details className="insp-sub-details">
              <summary>
                <span>
                  展开波浪计数与斐波那契测算
                  {displayPivots.length > 0
                    ? `（${hasWaveTags ? wave.current_wave : `${displayPivots.length}拐点`}）`
                    : ""}
                </span>
                <ChevronRight size={14} className="wt-det-chev" />
              </summary>
              <div className="insp-sub-body">
                {displayPivots.length > 0 && (
                  <div className="wt-points-block">
                    <div className="wt-block-head">
                      <b>{hasWaveTags ? "波浪各点位明细" : "近期波段关键拐点"}</b>
                      <span>
                        {hasWaveTags
                          ? `置信度 ${wave.confidence}`
                          : "未成型不强行标浪"}
                      </span>
                    </div>
                    <div className="wt-pivot-list">
                      {displayPivots.map((p, idx) => {
                        const prev = idx > 0 ? displayPivots[idx - 1] : null;
                        const legPct =
                          prev && prev.price > 0
                            ? ((p.price / prev.price - 1) * 100)
                            : null;
                        const badgeText = p.wave_label
                          ? p.wave_label === "0"
                            ? "起"
                            : `${p.wave_label}浪${p.confirmed ? "" : "*"}`
                          : p.kind === "H"
                            ? "高"
                            : "低";
                        return (
                          <div
                            className={`wt-pivot-row ${p.confirmed ? "" : "forming"}`}
                            key={`${p.date}-${p.kind}-${idx}`}
                          >
                            <span
                              className={`wt-pivot-tag ${
                                p.wave_label ? `tone-${wave.tone}` : ""
                              }`}
                            >
                              {badgeText}
                            </span>
                            <span className="wt-pivot-name">
                              {pivotTitle(p)}
                              {!p.confirmed && <em>进行中</em>}
                            </span>
                            <span className="wt-pivot-date">
                              {shortDate(p.date)}
                            </span>
                            <strong className="wt-pivot-price">
                              ${fmt(p.price, 2)}
                            </strong>
                            <span
                              className={`wt-pivot-chg ${
                                legPct == null
                                  ? "muted"
                                  : legPct >= 0
                                    ? "quote-up"
                                    : "quote-down"
                              }`}
                            >
                              {legPct != null
                                ? `${legPct >= 0 ? "+" : ""}${fmt(legPct, 1)}%`
                                : "锚点"}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {wave.fib_targets.length > 0 && (
                  <div className="wt-fib-list">
                    {wave.fib_targets.map((t, idx) => (
                      <div className="wt-fib-row" key={`${t.label}-${idx}`}>
                        <span>{t.label}</span>
                        <div className="wt-fib-nums">
                          <b>${fmt(t.price, 2)}</b>
                          {close != null && <em>{pctDiff(t.price, close)}</em>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </details>
          )}

          {/* 5. 二级参数/说明窗口快捷入口 */}
          <button
            type="button"
            className="wt-detail-link"
            onClick={() => setGuideOpen(true)}
          >
            <BookOpen size={14} />
            <span>查看通道分位、斜率、铁律校验与说明</span>
            <ChevronRight size={14} />
          </button>
        </>
      )}

      {guideOpen && wt.available && (
        <WaveTrendGuideModal
          stock={stock}
          wt={wt}
          onClose={() => setGuideOpen(false)}
        />
      )}
    </section>
  );
}
