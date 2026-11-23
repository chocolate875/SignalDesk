import { memo, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import {
  CandlestickChart,
  LineChart,
  BarChart,
  ScatterChart,
} from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
  MarkLineComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { HelpCircle, Maximize2, Minimize2, X } from "lucide-react";
import { IndicatorGuideMenu } from "./GuidePopover";
import type { ChartRow, Detail, EvalMode, Stock, WavePivot, WaveTrend } from "./types";
import { fmt, ticker, time } from "./types";

echarts.use([
  CandlestickChart,
  LineChart,
  BarChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

type OverlayMode = "MA" | "BOLL" | "NONE";

const NY_DATE_FMT = new Intl.DateTimeFormat("sv-SE", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function safeNumber(v: unknown): number | null {
  if (v == null || v === "") return null;
  const num = typeof v === "number" ? v : Number(v);
  return Number.isFinite(num) ? num : null;
}

function formatVolume(v: unknown): string {
  const num = safeNumber(v);
  if (num == null) return "—";
  if (num >= 1_000_000_000) {
    const val = num / 1_000_000_000;
    return val.toFixed(val >= 100 ? 1 : 2) + "B";
  }
  if (num >= 1_000_000) {
    const val = num / 1_000_000;
    return val.toFixed(val >= 100 ? 1 : 2) + "M";
  }
  if (num >= 1_000) return (num / 1_000).toFixed(1) + "K";
  return num.toFixed(0);
}

function buildCandleSeriesData(rows: ChartRow[]) {
  // 统一使用纯数组 [open, close, low, high]，避免 ECharts 6 混合对象项与虚线边框导致实体/影线碎裂及大图错位
  return rows.map((r) => [
    safeNumber(r.open),
    safeNumber(r.close),
    safeNumber(r.low),
    safeNumber(r.high),
  ]);
}

function buildVolumeSeriesData(rows: ChartRow[], up: string, down: string) {
  return rows.map((r) => {
    const open = safeNumber(r.open) ?? 0;
    const close = safeNumber(r.close) ?? open;
    const isRise = close >= open;
    const baseColor = isRise ? up : down;
    const forming = Boolean(r.intraday_forming);
    return {
      value: safeNumber(r.volume) ?? 0,
      itemStyle: forming
        ? {
            color: baseColor + "55",
            borderColor: baseColor,
            borderWidth: 1,
          }
        : {
            color: baseColor + "99",
          },
    };
  });
}

function OhlcHud({
  rows,
  dates,
  overlay,
  theme,
  evalMode = "confirmed",
  registerHover,
}: {
  rows: ChartRow[];
  dates: string[];
  overlay: OverlayMode;
  theme: string;
  evalMode?: EvalMode;
  registerHover: (setter: (idx: number | null) => void) => void;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  useEffect(() => {
    registerHover(setHoverIdx);
    return () => registerHover(() => {});
  }, [registerHover]);

  if (!rows.length) {
    return (
      <div className="ohlc-hud">
        <span className="muted">等待日线行情数据…</span>
      </div>
    );
  }

  const idx =
    hoverIdx != null && Number.isInteger(hoverIdx) && hoverIdx >= 0 && hoverIdx < rows.length
      ? hoverIdx
      : rows.length - 1;
  const row = rows[idx];
  const prev = idx > 0 ? rows[idx - 1] : null;
  const close = safeNumber(row.close);
  const open = safeNumber(row.open);
  const high = safeNumber(row.high);
  const low = safeNumber(row.low);
  const prevClose = safeNumber(prev?.close);
  const ret1 = safeNumber(row.return_1);
  const chgPct =
    close != null && prevClose != null && prevClose > 0
      ? (close / prevClose - 1) * 100
      : ret1 != null
        ? ret1 * 100
        : null;
  const isUp =
    chgPct != null
      ? chgPct >= 0
      : close != null && open != null
        ? close >= open
        : true;
  const isForming = Boolean(row.intraday_forming);
  const showFormingIndicators =
    isForming &&
    evalMode === "live" &&
    (safeNumber(row.ma20) != null || safeNumber(row.bb_middle) != null);
  const dirClass = isUp ? "quote-up" : "quote-down";

  return (
    <div className="ohlc-hud" aria-live="off">
      <span className="hud-date">{dates[idx] ?? "—"}</span>
      {isForming && (
        <span
          className="hud-live-pill"
          title={
            showFormingIndicators
              ? "当前处于「最新行情试算」口径（未收盘临时预览）"
              : "当天盘中实时生成（未收盘），均线 / MACD / RSI / 波浪评级仍严格按最近已确认收盘日线计算"
          }
        >
          {showFormingIndicators ? "实时试算" : "盘中"}
        </span>
      )}
      <span>
        开<b>{fmt(open, 2)}</b>
      </span>
      <span>
        高<b>{fmt(high, 2)}</b>
      </span>
      <span>
        低<b>{fmt(low, 2)}</b>
      </span>
      <span>
        {isForming ? "现" : "收"}
        <b className={dirClass}>{fmt(close, 2)}</b>
      </span>
      <span className={dirClass}>
        {chgPct != null
          ? `${chgPct >= 0 ? "+" : ""}${fmt(chgPct, 2)}%`
          : "—"}
      </span>
      <span>
        量<b>{formatVolume(row.volume)}</b>
      </span>
      {isForming && !showFormingIndicators ? (
        <span
          className="hud-forming-note"
          title="当天盘中实时生成（未收盘），均线 / MACD / RSI / 波浪评级仍严格按最近已确认收盘日线计算；可在右侧切换「最新行情试算」预览"
        >
          未收盘 · 指标按已收盘计
        </span>
      ) : (
        <>
          {overlay === "MA" && (
            <span className="hud-ma">
              <span className="hud-ma-item">
                <i style={{ background: theme === "dark" ? "#e2b857" : "#d97706" }} />
                MA20 {fmt(safeNumber(row.ma20), 2)}
              </span>
              <span className="hud-ma-item">
                <i style={{ background: theme === "dark" ? "#9e9cf2" : "#1e40af" }} />
                MA50 {fmt(safeNumber(row.ma50), 2)}
              </span>
              <span className="hud-ma-item">
                <i style={{ background: theme === "dark" ? "#5cb8e6" : "#64748b" }} />
                MA200 {fmt(safeNumber(row.ma200), 2)}
              </span>
            </span>
          )}
          {overlay === "BOLL" && (
            <span className="hud-ma">
              <span className="hud-ma-item">
                <i style={{ background: theme === "dark" ? "#858ee7" : "#1e40af" }} />
                上 {fmt(safeNumber(row.bb_upper), 2)}
              </span>
              <span className="hud-ma-item">
                <i style={{ background: theme === "dark" ? "#e2b857" : "#d97706" }} />
                中 {fmt(safeNumber(row.bb_middle), 2)}
              </span>
              <span className="hud-ma-item">
                <i style={{ background: theme === "dark" ? "#858ee7" : "#1e40af" }} />
                下 {fmt(safeNumber(row.bb_lower), 2)}
              </span>
            </span>
          )}
        </>
      )}
    </div>
  );
}

function WaveTrendSummaryPill({
  wt,
  symbol,
  forecastStop,
}: {
  wt: WaveTrend;
  symbol: string;
  forecastStop: number | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setOpen(false);
  }, [symbol]);

  useEffect(() => {
    if (!open) return;
    const updatePos = () => {
      const rect = btnRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(440, window.innerWidth - 24);
      const left = Math.max(
        12,
        Math.min(rect.left, window.innerWidth - width - 12),
      );
      const top = Math.min(rect.bottom + 6, Math.max(72, window.innerHeight - 310));
      setPos({ top: Math.round(top), left: Math.round(left) });
    };
    updatePos();
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("resize", updatePos);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", updatePos);
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const isDown = wt.trend.direction === "downtrend";
  const inv = wt.trend.invalidation_level;
  const invShort =
    inv != null
      ? isDown
        ? ` · 站上前高 $${fmt(inv, 2)} 反转`
        : ` · 破前低 $${fmt(inv, 2)} 失效`
      : "";

  // 查找对应这条结构线的已确认波段拐点，标明来源日期与浪号
  const targetKind = isDown ? "H" : "L";
  const confirmedMatches = (wt.wave.pivots ?? []).filter(
    (p) => p.confirmed && p.kind === targetKind,
  );
  const sourcePivot = confirmedMatches.length
    ? confirmedMatches[confirmedMatches.length - 1]
    : null;
  const pivotLabelText = sourcePivot?.wave_label
    ? sourcePivot.wave_label === "0"
      ? "波浪起点"
      : `第 ${sourcePivot.wave_label} 浪`
    : isDown
      ? "最近已确认波段前高"
      : "最近已确认波段前低";

  const quickTip =
    inv != null
      ? isDown
        ? `点击查看说明：$${fmt(inv, 2)} 是最近已确认波段前高，有效站上才代表空头下降结构反转`
        : `点击查看说明：$${fmt(inv, 2)} 是最近已确认波段前低（如前回调低点），收盘跌破代表当前趋势结构失效`
      : "点击查看当前波浪与趋势结构说明";

  return (
    <div ref={wrapRef} style={{ display: "inline-flex", minWidth: 0 }}>
      <button
        ref={btnRef}
        type="button"
        className={`chart-wt-pill tone-${wt.trend.tone}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={quickTip}
      >
        <span>
          {wt.trend.label} · {wt.wave.current_wave} ·{" "}
          {wt.trend.channel_position_label}
          {invShort}
        </span>
        <HelpCircle size={12} />
      </button>

      {open && pos && (
        <div
          className="guide-popover wt-explain-popover"
          style={{ top: pos.top, left: pos.left }}
          role="region"
          aria-label="趋势结构位含义说明"
        >
          <div className="guide-pop-head">
            <div>
              <b>
                {inv != null
                  ? isDown
                    ? `「站上前高 $${fmt(inv, 2)} 反转」是什么意思？`
                    : `「破前低 $${fmt(inv, 2)} 失效」是什么意思？`
                  : "当前波浪与趋势结构说明"}
              </b>
              <small>
                {wt.trend.label} · {wt.wave.pattern_label}（{wt.wave.current_wave}）
              </small>
            </div>
            <button
              type="button"
              className="legend-close-btn"
              onClick={() => setOpen(false)}
              aria-label="关闭说明"
            >
              <X size={15} />
            </button>
          </div>

          <div className="wt-explain-list">
            {inv != null && (
              <>
                <div className="wt-explain-row">
                  <b>1. 这个价格从哪来的？</b>
                  <p>
                    {sourcePivot
                      ? `取自 ${sourcePivot.date} 已确认的${pivotLabelText}（$${fmt(sourcePivot.price, 2)}），由严格因果拐点算法从历史日线中自动识别。`
                      : `取自近期已确认波段${isDown ? "高点" : "低点"}（$${fmt(inv, 2)}），由严格因果拐点算法自动识别。`}
                  </p>
                </div>
                <div className="wt-explain-row">
                  <b>2. 它在看盘时代表什么？</b>
                  <p>
                    {isDown
                      ? `这是空头「高点降低」结构的压制位。只有日线有效站上 $${fmt(inv, 2)} 上方，才说明空头下降结构被打破、出现趋势反转信号。`
                      : `这是道氏「低点抬高」多头结构的最后底线。只要不破 $${fmt(inv, 2)}，上升/震荡波段结构仍成立；若收盘有效跌破该前低，说明当前上涨趋势结构已失效。`}
                  </p>
                </div>
                <div className="wt-explain-row">
                  <b>3. 和图上左侧「参考止损」有什么区别？</b>
                  <p>
                    {forecastStop != null
                      ? `图上左侧「参考止损 $${fmt(forecastStop, 2)}」是按近期日均波幅（ATR14）测算的单笔交易风控止损线；而这里的 $${fmt(inv, 2)} 是按波段高低拐点划出的大趋势结构线。前者偏仓位止损，后者看大趋势是否破坏，因此两者数值可能不同。`
                      : "图上左侧「参考止损」是按近期日均波幅（ATR14）测算的单笔风控止损线；而本价位是按波段高低拐点划出的趋势结构分水岭，两者衡量维度不同。"}
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Chart({
  detail,
  liveQuote,
  marketSession,
  evalMode = "confirmed",
  liveEvalRow = null,
  theme,
  reverse,
}: {
  detail: Detail | null;
  liveQuote?: Stock["quote"];
  marketSession?: string;
  evalMode?: EvalMode;
  liveEvalRow?: ChartRow | null;
  theme: string;
  reverse: boolean;
}) {
  const root = useRef<HTMLDivElement>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const previousKey = useRef("");
  const structSigRef = useRef("");
  const latestRowsRef = useRef<ChartRow[]>([]);
  const latestDatesRef = useRef<string[]>([]);
  const evalModeRef = useRef<EvalMode>(evalMode);
  const pivotByIndexRef = useRef<Map<number, WavePivot>>(new Map());
  const hoverSetter = useRef<(idx: number | null) => void>(() => {});
  const [overlay, setOverlay] = useState<OverlayMode>("MA");
  const [showMacd, setShowMacd] = useState(true);
  const [showRsi, setShowRsi] = useState(false);
  const [showCost, setShowCost] = useState(true);
  const [showForecast, setShowForecast] = useState(true);
  const [showWaveTrend, setShowWaveTrend] = useState(true);
  const [activeRange, setActiveRange] = useState<number>(252);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [chartError, setChartError] = useState("");
  const [retrySeq, setRetrySeq] = useState(0);

  const registerHover = useMemo(
    () => (setter: (idx: number | null) => void) => {
      hoverSetter.current = setter;
    },
    [],
  );

  // 将 WebSocket 实时盘中报价合并到当日未收盘 K 线；开启「最新行情试算」时融合当日临时指标预览
  const displayRows = useMemo<ChartRow[]>(() => {
    const base = detail?.rows ?? [];
    if (!base.length) return [];

    const withLiveIndicators = (row: ChartRow): ChartRow => {
      if (evalMode !== "live" || !liveEvalRow) return row;
      return {
        ...row,
        ma20: liveEvalRow.ma20 ?? row.ma20 ?? null,
        ma50: liveEvalRow.ma50 ?? row.ma50 ?? null,
        ma200: liveEvalRow.ma200 ?? row.ma200 ?? null,
        bb_upper: liveEvalRow.bb_upper ?? row.bb_upper ?? null,
        bb_middle: liveEvalRow.bb_middle ?? row.bb_middle ?? null,
        bb_lower: liveEvalRow.bb_lower ?? row.bb_lower ?? null,
        macd: liveEvalRow.macd ?? row.macd ?? null,
        macd_signal: liveEvalRow.macd_signal ?? row.macd_signal ?? null,
        macd_hist: liveEvalRow.macd_hist ?? row.macd_hist ?? null,
        rsi: liveEvalRow.rsi ?? row.rsi ?? null,
        atr: liveEvalRow.atr ?? row.atr ?? null,
      };
    };

    if (
      detail?.mode !== "live" ||
      detail?.timeframe !== "day" ||
      !liveQuote ||
      liveQuote.seeded ||
      liveQuote.last == null ||
      !Number.isFinite(liveQuote.last) ||
      liveQuote.last <= 0 ||
      !liveQuote.timestamp
    ) {
      if (evalMode === "live" && liveEvalRow && detail?.mode === "live" && detail?.timeframe === "day") {
        const last = base[base.length - 1];
        if (last?.intraday_forming) {
          return [...base.slice(0, -1), withLiveIndicators(last)];
        }
        return [...base, { ...liveEvalRow, intraday_forming: true }];
      }
      return base;
    }
    const qMs = Date.parse(liveQuote.timestamp);
    if (!Number.isFinite(qMs)) return base;
    const qDay = NY_DATE_FMT.format(new Date(qMs));
    const lastRow = base[base.length - 1];
    const lastMs = lastRow?.timestamp ? Date.parse(lastRow.timestamp) : Number.NaN;
    const lastDay = Number.isFinite(lastMs) ? NY_DATE_FMT.format(new Date(lastMs)) : "";

    const pos = (v: unknown) => {
      const n = safeNumber(v);
      return n != null && n > 0 ? n : null;
    };
    const close = liveQuote.last;

    if (Boolean(lastRow.intraday_forming) && qDay === lastDay) {
      const open = pos(liveQuote.open) ?? pos(lastRow.open) ?? close;
      const high = Math.max(
        pos(liveQuote.high) ?? close,
        pos(lastRow.high) ?? close,
        open,
        close,
      );
      const low = Math.min(
        pos(liveQuote.low) ?? close,
        pos(lastRow.low) ?? close,
        open,
        close,
      );
      const prevClose =
        pos(liveQuote.prev_close) ??
        (base.length >= 2 ? pos(base[base.length - 2].close) : null);
      const liveVol = safeNumber(liveQuote.volume);
      const prevVol = safeNumber(lastRow.volume) ?? 0;
      const liveTurn = safeNumber(liveQuote.turnover);
      const prevTurn = safeNumber(lastRow.turnover) ?? 0;
      const updated: ChartRow = withLiveIndicators({
        ...lastRow,
        open,
        high,
        low,
        close,
        volume: liveVol != null ? Math.max(liveVol, prevVol) : lastRow.volume,
        turnover: liveTurn != null ? Math.max(liveTurn, prevTurn) : lastRow.turnover,
        return_1: prevClose ? close / prevClose - 1 : lastRow.return_1,
      });
      return [...base.slice(0, -1), updated];
    }

    if (
      !lastRow.intraday_forming &&
      lastDay &&
      qDay > lastDay &&
      (marketSession === "regular" || pos(liveQuote.open) != null)
    ) {
      const open = pos(liveQuote.open) ?? close;
      const high = Math.max(pos(liveQuote.high) ?? close, open, close);
      const low = Math.min(pos(liveQuote.low) ?? close, open, close);
      const prevClose = pos(liveQuote.prev_close) ?? pos(lastRow.close);
      const forming: ChartRow = withLiveIndicators({
        timestamp: liveQuote.timestamp,
        open,
        high,
        low,
        close,
        volume: safeNumber(liveQuote.volume) ?? 0,
        turnover: safeNumber(liveQuote.turnover) ?? 0,
        return_1: prevClose ? close / prevClose - 1 : null,
        intraday_forming: true,
      });
      return [...base, forming];
    }

    if (evalMode === "live" && liveEvalRow) {
      if (lastRow?.intraday_forming) {
        return [...base.slice(0, -1), withLiveIndicators(lastRow)];
      }
      const evMs = liveEvalRow.timestamp ? Date.parse(liveEvalRow.timestamp) : Number.NaN;
      const evDay = Number.isFinite(evMs) ? NY_DATE_FMT.format(new Date(evMs)) : "";
      if (evDay && (!lastDay || evDay > lastDay)) {
        return [...base, { ...liveEvalRow, intraday_forming: true }];
      }
    }

    return base;
  }, [detail?.rows, detail?.mode, detail?.timeframe, liveQuote, marketSession, evalMode, liveEvalRow]);

  const dates = useMemo(() => {
    if (!displayRows.length) return [];
    return displayRows.map((r) => {
      const ms = r?.timestamp ? Date.parse(r.timestamp) : Number.NaN;
      return Number.isFinite(ms) ? NY_DATE_FMT.format(new Date(ms)) : "";
    });
  }, [displayRows]);

  latestRowsRef.current = displayRows;
  latestDatesRef.current = dates;
  evalModeRef.current = evalMode;

  useEffect(() => {
    hoverSetter.current(null);
    setChartError("");
  }, [detail?.stock?.symbol, detail?.mode]);

  useEffect(() => {
    const onFs = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  useEffect(() => {
    if (!root.current) return;
    const el = root.current;
    const instance = echarts.init(el, undefined, {
      renderer: "canvas",
    });
    chart.current = instance;
    structSigRef.current = "";
    previousKey.current = "";
    instance.on("updateAxisPointer", (event: any) => {
      const idx = event?.axesInfo?.[0]?.value;
      hoverSetter.current(
        typeof idx === "number" && Number.isInteger(idx) && idx >= 0 ? idx : null,
      );
    });
    instance.on("globalout", () => {
      hoverSetter.current(null);
    });
    let rafId: number | null = null;
    const resize = new ResizeObserver(() => {
      if (rafId != null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        if (
          !instance.isDisposed() &&
          el.clientWidth > 0 &&
          el.clientHeight > 0
        ) {
          try {
            instance.resize();
          } catch {
            // 忽略窗口折叠或瞬时 0 尺寸引起的 ECharts resize 异常
          }
        }
      });
    });
    resize.observe(el);
    return () => {
      if (rafId != null) cancelAnimationFrame(rafId);
      resize.disconnect();
      if (!instance.isDisposed()) instance.dispose();
      chart.current = null;
      structSigRef.current = "";
      previousKey.current = "";
    };
  }, [retrySeq]);

  useEffect(() => {
    const instance = chart.current;
    if (!instance || instance.isDisposed()) return;
    if (!detail || !displayRows.length) {
      try {
        instance.clear();
      } catch {
        // 忽略清理异常
      }
      previousKey.current = "";
      structSigRef.current = "";
      return;
    }
    const rows = displayRows;
    const dark = theme === "dark";
    const up = dark
      ? reverse
        ? "#ef5f6c"
        : "#22c58b"
      : reverse
        ? "#dc2626"
        : "#10b981";
    const down = dark
      ? reverse
        ? "#22c58b"
        : "#ef5f6c"
      : reverse
        ? "#10b981"
        : "#dc2626";
    const axis = dark ? "#8da0b6" : "#64748b";
    const gridColor = dark ? "#1f2b3a" : "#e5e7eb";
    const ma20Color = dark ? "#e2b857" : "#d97706";
    const ma50Color = dark ? "#9e9cf2" : "#1e40af";
    const ma200Color = dark ? "#5cb8e6" : "#64748b";
    const bollBandColor = dark ? "#858ee7" : "#1e40af";
    const key = [
      detail.stock?.symbol ?? "",
      detail.mode ?? "",
      detail.timeframe ?? "",
      detail.session ?? "",
    ].join("/");

    const flRef = detail.stock.forecast?.levels;
    const structSig = JSON.stringify([
      key,
      detail.rows.length,
      detail.rows[detail.rows.length - 1]?.timestamp ?? "",
      dates.length,
      dates[0] ?? "",
      dates[dates.length - 1] ?? "",
      detail.stock.wave_trend?.trend?.channel?.end_date ?? "",
      detail.stock.wave_trend?.wave?.pivots?.length ?? 0,
      detail.stock.long_plan.stop ?? null,
      detail.stock.long_plan.target ?? null,
      detail.stock.broker_quantity,
      detail.stock.cost_price ?? null,
      flRef?.available ?? false,
      flRef?.buy_high ?? null,
      flRef?.sell_low ?? null,
      flRef?.stop_loss ?? null,
      overlay,
      evalMode,
      evalMode === "live" ? (liveEvalRow?.ma20 ?? null) : null,
      evalMode === "live" ? (liveEvalRow?.rsi ?? null) : null,
      showMacd,
      showRsi,
      showCost,
      showForecast,
      showWaveTrend,
      theme,
      reverse,
      retrySeq,
    ]);

    const candleData = buildCandleSeriesData(rows);
    const volumeData = buildVolumeSeriesData(rows, up, down);

    // 仅 WebSocket 推送刷新当日未收盘 K 线的实时价格/成交量时，做轻量增量更新，
    // 绝不调用 notMerge:true 重建整图，避免鼠标悬停/点选最新 K 线时 Tooltip 与十字准星瞬间消失
    if (structSig === structSigRef.current && key === previousKey.current) {
      try {
        instance.setOption(
          {
            series: [
              { id: "price", data: candleData },
              { id: "volume", data: volumeData },
            ],
          },
          { notMerge: false },
        );
        setChartError("");
      } catch (err: any) {
        console.error("[SignalDesk Chart live update]", err);
      }
      return;
    }

    let old: any = null;
    try {
      old = instance.getOption();
    } catch {
      old = null;
    }
    const isSameSymbol = key === previousKey.current;
    const zoom =
      isSameSymbol && old?.xAxis?.[0]?.data?.length >= 2
        ? old?.dataZoom?.[0]
        : null;
    previousKey.current = key;
    if (!isSameSymbol) {
      setActiveRange(252);
    }

    let left = Math.max(0, rows.length - 252);
    let right = rows.length - 1;
    if (
      zoom &&
      typeof zoom.start === "number" &&
      typeof zoom.end === "number" &&
      Number.isFinite(zoom.start) &&
      Number.isFinite(zoom.end)
    ) {
      const oldDates: string[] = old.xAxis[0].data;
      const oldLeft = Math.max(
        0,
        Math.min(
          oldDates.length - 1,
          Math.round(((oldDates.length - 1) * zoom.start) / 100),
        ),
      );
      const oldRight = Math.max(
        oldLeft,
        Math.min(
          oldDates.length - 1,
          Math.round(((oldDates.length - 1) * zoom.end) / 100),
        ),
      );
      if (oldRight >= oldDates.length - 1) {
        left = Math.max(0, right - (oldRight - oldLeft));
      } else {
        const mappedLeft = dates.indexOf(oldDates[oldLeft]);
        const mappedRight = dates.indexOf(oldDates[oldRight]);
        if (mappedLeft >= 0) left = mappedLeft;
        if (mappedRight >= 0) right = Math.max(left, mappedRight);
      }
    }
    left = Math.max(0, Math.min(left, rows.length - 1));
    right = Math.max(left, Math.min(right, rows.length - 1));

    const val = (field: string) =>
      rows.map((r) => safeNumber(r[field]));
    const line = (
      name: string,
      field: string,
      color: string,
      gridIndex = 0,
      show = true,
    ) => ({
      id: field,
      name,
      type: "line",
      xAxisIndex: gridIndex,
      yAxisIndex: gridIndex,
      data: show ? val(field) : [],
      symbol: "none",
      connectNulls: false,
      lineStyle: { width: 1.5, color },
      itemStyle: { color },
      animation: false,
    });

    type PaneSpec = { kind: "price" | "vol" | "macd" | "rsi"; top: number | string; height: string };
    const panes: PaneSpec[] =
      showMacd && showRsi
        ? [
            { kind: "price", top: 28, height: "36.5%" },
            { kind: "vol", top: "50.5%", height: "10%" },
            { kind: "macd", top: "67.5%", height: "10.5%" },
            { kind: "rsi", top: "84.5%", height: "9.5%" },
          ]
        : showMacd || showRsi
          ? [
              { kind: "price", top: 30, height: "48%" },
              { kind: "vol", top: "63%", height: "11%" },
              { kind: showMacd ? "macd" : "rsi", top: "81.5%", height: "12%" },
            ]
          : [
              { kind: "price", top: 30, height: "64%" },
              { kind: "vol", top: "79%", height: "14%" },
            ];

    const paneIndex = (kind: PaneSpec["kind"]) =>
      panes.findIndex((p) => p.kind === kind);
    const macdIdx = paneIndex("macd");
    const rsiIdx = paneIndex("rsi");
    const lastIdx = panes.length - 1;

    const costPrice =
      showCost &&
      detail.stock.broker_quantity > 0 &&
      detail.stock.cost_price != null
        ? detail.stock.cost_price
        : null;

    const planLines = [
      {
        label: "失效价",
        price: detail.stock.long_plan.stop,
        color: down,
      },
      {
        label: "目标价",
        price: detail.stock.long_plan.target,
        color: up,
      },
      {
        label: "成本价",
        price: costPrice,
        color: "#e2b857",
      },
    ]
      .filter(({ price }) => price != null)
      .map(({ label, price, color }) => ({
        name: `${label} $${fmt(price, 2)}`,
        yAxis: price,
        lineStyle: { color, width: 1.5, type: "dashed" },
        label: { position: "insideMiddleTop" },
      }));

    const fl = detail.stock.forecast?.levels;
    const forecastBuyColor = "#10b981";
    const forecastSellColor = dark ? "#60a5fa" : "#1e40af";
    const forecastStopColor = dark ? "#ef5f6c" : "#dc2626";
    const forecastLines =
      showForecast && fl?.available
        ? [
            { label: "参考买点", price: fl.buy_high, color: forecastBuyColor, showLabel: true },
            { label: "深度买点", price: fl.buy_low, color: forecastBuyColor, showLabel: false },
            { label: "参考卖点", price: fl.sell_low, color: forecastSellColor, showLabel: true },
            { label: "目标卖点", price: fl.sell_high, color: forecastSellColor, showLabel: true },
            { label: "参考止损", price: fl.stop_loss, color: forecastStopColor, showLabel: true },
          ]
            .filter(({ price }) => price != null)
            .map(({ label, price, color, showLabel }) => ({
              name: `${label} $${fmt(price, 2)}`,
              yAxis: price,
              lineStyle: { color, width: 1.2, type: "dotted", opacity: 0.85 },
              label: { show: showLabel, position: "insideStartTop" },
            }))
        : [];

    const markLines = [...planLines, ...forecastLines];

    const series: any[] = [
      {
        id: "price",
        name: "OHLC",
        type: "candlestick",
        xAxisIndex: 0,
        yAxisIndex: 0,
        large: false,
        selectedMode: false,
        barMaxWidth: 28,
        data: candleData,
        markLine: {
          silent: true,
          symbol: "none",
          label: {
            position: "insideStartTop",
            formatter: "{b}",
            color: dark ? "#edf2f7" : "#0f172a",
            backgroundColor: dark ? "#141d28e6" : "#ffffffeb",
            borderColor: gridColor,
            borderWidth: 1,
            borderRadius: 4,
            padding: [2, 6],
            fontSize: 12,
          },
          data: markLines,
        },
        itemStyle: {
          color: up,
          color0: down,
          borderColor: up,
          borderColor0: down,
        },
      },
      line("MA20", "ma20", ma20Color, 0, overlay === "MA"),
      line("MA50", "ma50", ma50Color, 0, overlay === "MA"),
      line("MA200", "ma200", ma200Color, 0, overlay === "MA"),
      line("布林上轨", "bb_upper", bollBandColor, 0, overlay === "BOLL"),
      line("布林中轨", "bb_middle", ma20Color, 0, overlay === "BOLL"),
      line("布林下轨", "bb_lower", bollBandColor, 0, overlay === "BOLL"),
      {
        id: "volume",
        name: "成交量",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        large: false,
        selectedMode: false,
        barMaxWidth: 28,
        data: volumeData,
      },
    ];

    // Elliott Wave & Parallel Trend Channel overlay (strictly causal backend coordinates)
    const wt = detail.stock.wave_trend;
    const pivotByIndex = new Map<number, WavePivot>();
    if (showWaveTrend && wt?.available) {
      const ch = wt.trend.channel;
      if (ch?.available && ch.start_date && ch.end_date) {
        const sIdx = dates.indexOf(ch.start_date);
        const eIdx = dates.indexOf(ch.end_date);
        if (
          sIdx >= 0 &&
          eIdx > sIdx &&
          ch.start_upper != null &&
          ch.end_upper != null &&
          ch.start_mid != null &&
          ch.end_mid != null &&
          ch.start_lower != null &&
          ch.end_lower != null
        ) {
          const span = eIdx - sIdx;
          const upperArr: (number | null)[] = new Array(rows.length).fill(null);
          const midArr: (number | null)[] = new Array(rows.length).fill(null);
          const lowerArr: (number | null)[] = new Array(rows.length).fill(null);
          for (let i = sIdx; i <= eIdx; i++) {
            const t = (i - sIdx) / span;
            upperArr[i] = Number(
              (ch.start_upper + (ch.end_upper - ch.start_upper) * t).toFixed(2),
            );
            midArr[i] = Number(
              (ch.start_mid + (ch.end_mid - ch.start_mid) * t).toFixed(2),
            );
            lowerArr[i] = Number(
              (ch.start_lower + (ch.end_lower - ch.start_lower) * t).toFixed(2),
            );
          }
          const channelColor =
            wt.trend.direction === "uptrend"
              ? dark
                ? "#34d399"
                : "#10b981"
              : wt.trend.direction === "downtrend"
                ? dark
                  ? "#ef5f6c"
                  : "#dc2626"
                : dark
                  ? "#60a5fa"
                  : "#3b82f6";
          series.push(
            {
              id: "trend-channel-upper",
              name: "通道上轨",
              type: "line",
              xAxisIndex: 0,
              yAxisIndex: 0,
              data: upperArr,
              symbol: "none",
              silent: true,
              lineStyle: {
                width: 1.3,
                type: "dashed",
                color: channelColor,
                opacity: 0.72,
              },
              animation: false,
            },
            {
              id: "trend-channel-mid",
              name: "通道中轨",
              type: "line",
              xAxisIndex: 0,
              yAxisIndex: 0,
              data: midArr,
              symbol: "none",
              silent: true,
              lineStyle: {
                width: 1,
                type: "dotted",
                color: channelColor,
                opacity: 0.52,
              },
              animation: false,
            },
            {
              id: "trend-channel-lower",
              name: "通道下轨",
              type: "line",
              xAxisIndex: 0,
              yAxisIndex: 0,
              data: lowerArr,
              symbol: "none",
              silent: true,
              lineStyle: {
                width: 1.3,
                type: "dashed",
                color: channelColor,
                opacity: 0.72,
              },
              animation: false,
            },
          );
        }
      }

      const mappedPivots = (wt.wave.pivots ?? [])
        .map((p) => ({ idx: dates.indexOf(p.date), pivot: p }))
        .filter((item) => item.idx >= 0);

      for (const item of mappedPivots) {
        pivotByIndex.set(item.idx, item.pivot);
      }

      if (mappedPivots.length >= 2) {
        const waveColor = dark ? "#60a5fa" : "#1e40af";
        const confirmedArr: (number | null)[] = new Array(rows.length).fill(null);
        const confirmedPoints = mappedPivots.filter((m) => m.pivot.confirmed);
        for (const m of confirmedPoints) {
          confirmedArr[m.idx] = m.pivot.price;
        }
        if (confirmedPoints.length >= 2) {
          series.push({
            id: "wave-confirmed",
            name: "已确认波浪",
            type: "line",
            xAxisIndex: 0,
            yAxisIndex: 0,
            data: confirmedArr,
            symbol: "none",
            connectNulls: true,
            silent: true,
            z: 4,
            lineStyle: { width: 1.9, color: waveColor, opacity: 0.82 },
            animation: false,
          });
        }

        const lastM = mappedPivots[mappedPivots.length - 1];
        const prevM = mappedPivots[mappedPivots.length - 2];
        if (!lastM.pivot.confirmed && prevM) {
          const formingArr: (number | null)[] = new Array(rows.length).fill(null);
          formingArr[prevM.idx] = prevM.pivot.price;
          formingArr[lastM.idx] = lastM.pivot.price;
          series.push({
            id: "wave-forming",
            name: "进行中波段",
            type: "line",
            xAxisIndex: 0,
            yAxisIndex: 0,
            data: formingArr,
            symbol: "none",
            connectNulls: true,
            silent: true,
            z: 4,
            lineStyle: {
              width: 1.7,
              type: "dashed",
              color: waveColor,
              opacity: 0.72,
            },
            animation: false,
          });
        }

        const shortStruct: Record<string, string> = {
          HH: "高抬",
          HL: "低抬",
          LH: "高低",
          LL: "低低",
          H: "高",
          L: "低",
        };
        const formatPivotBadge = (p: WavePivot) => {
          const suffix = p.confirmed ? "" : "*";
          const priceStr = `$${fmt(p.price, 2)}`;
          if (p.wave_label) {
            if (p.wave_label === "0") return `起 ${priceStr}`;
            return `${p.wave_label}浪${suffix} ${priceStr}`;
          }
          return `${shortStruct[p.structure] ?? p.structure}${suffix} ${priceStr}`;
        };

        const hasAnyWave = mappedPivots.some((m) => Boolean(m.pivot.wave_label));
        const structCutoff = Math.max(0, mappedPivots.length - (hasAnyWave ? 0 : 4));
        const shownSameKindIndices: { H: number[]; L: number[] } = { H: [], L: [] };
        const scatterData = mappedPivots.map(({ idx, pivot }, mIdx) => {
          const hasWave = Boolean(pivot.wave_label);
          const showLabel = hasWave || (!hasAnyWave && mIdx >= structCutoff);
          const isHigh = pivot.kind === "H";
          const nearRightEdge = idx >= rows.length - 8;
          const bucket = isHigh ? shownSameKindIndices.H : shownSameKindIndices.L;
          let labelPos: string = isHigh ? "top" : "bottom";
          let labelDist = 6;
          if (showLabel) {
            const nearCount = bucket.filter((prevIdx) => Math.abs(idx - prevIdx) <= 28).length;
            if (nearCount > 0) {
              // 相邻同侧拐点错开左右与距离，防止带价格胶囊重叠；靠右边界拐点保持右对齐向左展开
              labelPos = nearRightEdge
                ? isHigh
                  ? "top"
                  : "bottom"
                : isHigh
                  ? nearCount % 2 === 1
                    ? "topRight"
                    : "topLeft"
                  : nearCount % 2 === 1
                    ? "bottomRight"
                    : "bottomLeft";
              labelDist = 6 + nearCount * 14;
            }
            bucket.push(idx);
          }
          const accent = hasWave
            ? wt.wave.pattern === "impulse_down"
              ? dark
                ? "#ef5f6c"
                : "#dc2626"
              : wt.wave.pattern === "correction_abc"
                ? dark
                  ? "#fbbf24"
                  : "#d97706"
                : dark
                  ? "#60a5fa"
                  : "#1e40af"
            : dark
              ? "#94a3b8"
              : "#64748b";
          return {
            value: [idx, pivot.price],
            symbolSize: hasWave ? 7 : 4,
            itemStyle: {
              color: hasWave ? accent : dark ? "#1e293b" : "#ffffff",
              borderColor: accent,
              borderWidth: hasWave ? 1.5 : 1.2,
            },
            label: {
              show: showLabel,
              position: labelPos,
              align: nearRightEdge ? "right" : undefined,
              distance: labelDist,
              formatter: formatPivotBadge(pivot),
              fontSize: 12,
              fontWeight: hasWave ? 700 : 500,
              color: hasWave ? accent : dark ? "#cbd5e1" : "#475569",
              backgroundColor: dark
                ? hasWave
                  ? "#111720ee"
                  : "#111720cc"
                : hasWave
                  ? "#fffffff2"
                  : "#f8fafce6",
              borderColor: hasWave ? accent : gridColor,
              borderWidth: 1,
              borderRadius: 999,
              padding: [1, 6],
            },
          };
        });

        series.push({
          id: "wave-pivots",
          name: "波浪拐点",
          type: "scatter",
          xAxisIndex: 0,
          yAxisIndex: 0,
          z: 6,
          data: scatterData,
          labelLayout: { moveOverlap: "shiftY" },
          silent: true,
          animation: false,
        });
      }
    }
    pivotByIndexRef.current = pivotByIndex;

    if (macdIdx >= 0) {
      series.push(
        {
          id: "hist",
          name: "MACD柱",
          type: "bar",
          xAxisIndex: macdIdx,
          yAxisIndex: macdIdx,
          large: false,
          selectedMode: false,
          data: rows.map((r) => {
            const mh = safeNumber(r.macd_hist);
            return {
              value: mh,
              itemStyle: { color: (mh ?? 0) >= 0 ? up : down },
            };
          }),
        },
        line("MACD", "macd", ma20Color, macdIdx),
        line("Signal", "macd_signal", ma50Color, macdIdx),
      );
    }

    if (rsiIdx >= 0) {
      series.push({
        ...line("RSI14", "rsi", ma50Color, rsiIdx),
        markLine: {
          silent: true,
          symbol: "none",
          label: { show: false },
          lineStyle: { color: axis, type: "dashed", opacity: 0.5 },
          data: [{ yAxis: 30 }, { yAxis: 70 }],
        },
      });
    }

    const structFull: Record<string, string> = {
      HH: "高点抬高 HH",
      HL: "低点抬高 HL",
      LH: "高点降低 LH",
      LL: "低点降低 LL",
      H: "阶段高点",
      L: "阶段低点",
    };

    const option: any = {
      animation: false,
      backgroundColor: "transparent",
      textStyle: {
        fontFamily:
          "'Inter', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', Roboto, sans-serif",
        fontSize: 12,
      },
      tooltip: {
        trigger: "axis",
        triggerOn: "mousemove",
        transitionDuration: 0,
        axisPointer: { type: "cross" },
        confine: true,
        renderMode: "html",
        formatter: (items: any) => {
          try {
            const list = Array.isArray(items) ? items : items ? [items] : [];
            const i = list[0]?.dataIndex;
            const liveRows = latestRowsRef.current;
            const liveDates = latestDatesRef.current;
            if (typeof i !== "number" || !Number.isInteger(i) || i < 0 || i >= liveRows.length) {
              return "";
            }
            const row = liveRows[i];
            if (!row) return "";
            const value = (field: string, digits = 2) =>
              fmt(safeNumber(row[field]), digits);
            const isForming = Boolean(row.intraday_forming);
            const isLiveEval = isForming && evalModeRef.current === "live" && safeNumber(row.rsi) != null;
            const lines = [
              isForming
                ? isLiveEval
                  ? `<b>${liveDates[i] ?? "—"}</b> · 最新行情试算（未收盘临时预览）`
                  : `<b>${liveDates[i] ?? "—"}</b> · 盘中实时（未收盘，不计入正式指标）`
                : `<b>${liveDates[i] ?? "—"}</b> · 纽约收盘（前复权）`,
              `开 ${value("open")} · 高 ${value("high")} · 低 ${value("low")} · ${isForming ? "现" : "收"} ${value("close")}`,
              `成交量 ${formatVolume(row.volume)} · 成交额 $${formatVolume(row.turnover)}`,
              isForming && !isLiveEval
                ? "MA / MACD / RSI / 波浪评级仍按最近已确认收盘日线计算"
                : `RSI14 ${value("rsi")} · MACD柱 ${value("macd_hist", 3)}${isLiveEval ? "（试算）" : ""}`,
            ];
            const pv = pivotByIndexRef.current.get(i);
            if (pv) {
              const wText = pv.wave_label
                ? pv.wave_label === "0"
                  ? "波浪起点"
                  : `第 ${pv.wave_label} 浪`
                : "波段拐点";
              const stateText = pv.confirmed ? "已确认" : "进行中";
              lines.push(
                `<b>${wText}</b> · ${structFull[pv.structure] ?? pv.structure} · $${fmt(pv.price, 2)}（${stateText}）`,
              );
            }
            return lines.join("<br>");
          } catch {
            return "";
          }
        },
        backgroundColor: dark ? "#16212f" : "#ffffff",
        borderColor: gridColor,
        textStyle: { color: dark ? "#e2eaf3" : "#0f172a", fontSize: 13 },
        extraCssText: dark
          ? "border-radius: 8px;"
          : "box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08); border-radius: 8px;",
      },
      axisPointer: {
        link: [{ xAxisIndex: "all" }],
        label: { backgroundColor: dark ? "#33475e" : "#1e40af", fontSize: 12 },
      },
      grid: panes.map((p) => ({
        left: 14,
        right: 80,
        top: p.top,
        height: p.height,
      })),
      xAxis: panes.map((_, i) => ({
        type: "category",
        data: dates,
        gridIndex: i,
        boundaryGap: true,
        axisLine: { lineStyle: { color: gridColor } },
        axisTick: { show: false },
        axisLabel: {
          show: i === lastIdx,
          color: axis,
          fontSize: 12,
          hideOverlap: true,
          margin: 8,
        },
        splitLine: { show: false },
        axisPointer: {
          show: true,
          snap: true,
          // 仅最底部窗格显示日期浮标，避免多子图在最右侧重复堆叠日期块遮盖 Y 轴数字
          label: { show: i === lastIdx },
        },
      })),
      yAxis: panes.map((p, i) => ({
        scale: p.kind !== "vol",
        gridIndex: i,
        position: "right",
        splitNumber: p.kind === "price" ? 5 : 2,
        boundaryGap: p.kind === "price" ? ["10%", "12%"] : undefined,
        min:
          p.kind === "rsi" || p.kind === "vol"
            ? 0
            : p.kind === "price"
              ? (v: { min: number; max: number }) =>
                  Number.isFinite(v.min) &&
                  Number.isFinite(v.max) &&
                  v.min >= 0 &&
                  v.min - Math.max(v.max - v.min, 0) * 0.12 <= 0
                    ? 0
                    : (undefined as any)
              : undefined,
        max: p.kind === "rsi" ? 100 : undefined,
        splitLine: {
          show: true,
          lineStyle: { color: gridColor, type: "dashed" },
        },
        axisLabel: {
          color: axis,
          fontSize: 12,
          margin: 12,
          formatter: (v: number) =>
            p.kind === "vol"
              ? formatVolume(v)
              : p.kind === "rsi"
                ? v.toFixed(0)
                : v.toFixed(2),
        },
        axisLine: { show: false },
        axisTick: { show: false },
      })),
      dataZoom: [
        {
          type: "inside",
          xAxisIndex: panes.map((_, i) => i),
          startValue: left,
          endValue: right,
        },
      ],
      series,
    };
    try {
      instance.setOption(option, { notMerge: true });
      structSigRef.current = structSig;
      setChartError("");
    } catch (err: any) {
      console.error("[SignalDesk Chart setOption]", err);
      setChartError(err?.message || "K 线图渲染遇到异常");
    }
  }, [
    detail,
    displayRows,
    dates,
    overlay,
    evalMode,
    liveEvalRow,
    showMacd,
    showRsi,
    showCost,
    showForecast,
    showWaveTrend,
    theme,
    reverse,
    retrySeq,
  ]);

  const paneTitles = useMemo(() => {
    if (showMacd && showRsi) {
      return [
        { label: "日线价格 / 美元", top: "4px", isPrice: true },
        { label: "成交量 / 股", top: "46.5%", isPrice: false },
        { label: "MACD (12, 26, 9)", top: "63.5%", isPrice: false },
        { label: "RSI (14)", top: "80.5%", isPrice: false },
      ];
    }
    if (showMacd || showRsi) {
      return [
        { label: "日线价格 / 美元", top: "4px", isPrice: true },
        { label: "成交量 / 股", top: "58.5%", isPrice: false },
        {
          label: showMacd ? "MACD (12, 26, 9)" : "RSI (14)",
          top: "77%",
          isPrice: false,
        },
      ];
    }
    return [
      { label: "日线价格 / 美元", top: "4px", isPrice: true },
      { label: "成交量 / 股", top: "74.5%", isPrice: false },
    ];
  }, [showMacd, showRsi]);

  const activeWaveTrend = detail?.stock?.wave_trend;

  const zoomTo = (countLimit: number) => {
    const count = displayRows.length;
    const instance = chart.current;
    if (!count || !instance || instance.isDisposed()) return;
    setActiveRange(countLimit);
    try {
      instance.dispatchAction({
        type: "dataZoom",
        startValue: countLimit ? Math.max(0, count - countLimit) : 0,
        endValue: count - 1,
      });
    } catch {
      // 忽略缩放动作在图表重建期间的瞬态异常
    }
  };

  return (
    <div ref={wrapper} className="chart-wrap">
      <div className="chart-toolbar">
        {isFullscreen && detail && (
          <div className="fullscreen-chart-title">
            <b>{ticker(detail.stock.symbol)} · 日线</b>
            <span>
              {detail.mode === "demo" ? "合成行情" : "常规时段 · 前复权"}
            </span>
            <span>
              {evalMode === "live" ? "试算" : "收盘"} ${fmt(detail.summary?.close, 2)} ·{" "}
              {time(detail.summary?.as_of, "America/New_York")}（纽约）
            </span>
          </div>
        )}

        <div className="toolbar-group" aria-label="时间范围">
          {(
            [
              [63, "近3月", "查看近3个月日线"],
              [126, "近6月", "查看近6个月日线"],
              [252, "近1年", "查看近1年日线"],
              [0, "全部", "查看全部历史日线"],
              [60, "最新", "回到最新位置"],
            ] as const
          ).map(([n, label, tip]) => (
            <button
              key={label}
              type="button"
              className={activeRange === n ? "active" : ""}
              disabled={!displayRows.length}
              onClick={() => zoomTo(n)}
              title={tip}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="toolbar-group" aria-label="主图叠加指标">
          {(
            [
              ["MA", "MA", "叠加 MA20 / MA50 / MA200 均线"],
              ["BOLL", "BOLL", "叠加布林带上下轨"],
              ["NONE", "净图", "仅显示裸 K 线"],
            ] as const
          ).map(([id, label, tip]) => (
            <button
              key={id}
              type="button"
              className={overlay === id ? "active" : ""}
              onClick={() => setOverlay(id)}
              title={tip}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="toolbar-group" aria-label="副图与参考线">
          <button
            type="button"
            className={showMacd ? "active" : ""}
            onClick={() => setShowMacd(!showMacd)}
            title="显示或隐藏 MACD 副图"
          >
            MACD
          </button>
          <button
            type="button"
            className={showRsi ? "active" : ""}
            onClick={() => setShowRsi(!showRsi)}
            title="显示或隐藏 RSI 副图（默认关闭，留出更大主图视野）"
          >
            RSI
          </button>
          {(detail?.stock?.broker_quantity ?? 0) > 0 &&
            detail?.stock?.cost_price != null && (
              <button
                type="button"
                className={showCost ? "active" : ""}
                onClick={() => setShowCost(!showCost)}
                title="显示/隐藏成本线"
              >
                成本
              </button>
            )}
          {detail?.stock?.forecast?.levels?.available && (
            <button
              type="button"
              className={showForecast ? "active" : ""}
              onClick={() => setShowForecast(!showForecast)}
              title="显示/隐藏预测买卖点参考线"
            >
              点位
            </button>
          )}
          {activeWaveTrend?.available && (
            <button
              type="button"
              className={showWaveTrend ? "active" : ""}
              onClick={() => setShowWaveTrend(!showWaveTrend)}
              title="显示/隐藏波浪标号（1-5 / A-C / 高低结构）与趋势通道"
            >
              波浪
            </button>
          )}
        </div>

        <div className="toolbar-right-actions">
          <IndicatorGuideMenu />
          <button
            type="button"
            className="toolbar-fs-btn"
            onClick={() => {
              const p = document.fullscreenElement
                ? document.exitFullscreen()
                : wrapper.current?.requestFullscreen();
              p?.catch(() => {});
            }}
            title={isFullscreen ? "退出全屏" : "全屏看图"}
          >
            {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            <span>{isFullscreen ? "退出全屏" : "全屏"}</span>
          </button>
        </div>
      </div>

      <OhlcHud
        rows={displayRows}
        dates={dates}
        overlay={overlay}
        theme={theme}
        evalMode={evalMode}
        registerHover={registerHover}
      />

      <div className="chart-plot">
        <div className="chart-labels">
          {paneTitles.map((p) =>
            p.isPrice ? (
              <div
                key={p.label}
                className="chart-price-head"
                style={{ top: p.top }}
              >
                <span>{p.label}</span>
                {showWaveTrend && activeWaveTrend?.available && (
                  <WaveTrendSummaryPill
                    wt={activeWaveTrend}
                    symbol={detail?.stock?.symbol ?? ""}
                    forecastStop={detail?.stock?.forecast?.levels?.stop_loss}
                  />
                )}
              </div>
            ) : (
              <span key={p.label} style={{ top: p.top }}>
                {p.label}
              </span>
            ),
          )}
        </div>
        <div
          ref={root}
          className="price-chart"
          role="img"
          aria-label="价格、成交量、MACD与RSI联动图"
        />
        {chartError && (
          <div className="chart-empty chart-error-overlay" role="alert">
            <span>图表渲染遇到异常：{chartError}</span>
            <button
              type="button"
              className="button secondary"
              onClick={() => {
                setChartError("");
                setRetrySeq((n) => n + 1);
              }}
            >
              重新加载图表
            </button>
          </div>
        )}
        {!chartError && !displayRows.length && (
          <div className="chart-empty">
            该标的日线历史尚未就绪，正在等待有效行情
          </div>
        )}
      </div>
    </div>
  );
}

export default memo(Chart);
