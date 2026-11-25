import { memo, useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts/core";
import {
  CandlestickChart,
  LineChart,
  BarChart,
  ScatterChart,
  CustomChart,
} from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
  MarkLineComponent,
  MarkAreaComponent,
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
  CustomChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
  MarkLineComponent,
  MarkAreaComponent,
  CanvasRenderer,
]);

type OverlayMode = "MA" | "BOLL" | "NONE";

const DEFAULT_RANGE_BARS = 126;
const PRESET_RANGES = [63, 126, 252, 0] as const;

type SavedViewWindow = {
  spanBars: number;
  anchoredRight: boolean;
  startDate: string;
  endDate: string;
};

/** 跨标的共享的视图缩放与日期位置状态，确保切换不同股票时保持一致的缩放比例与历史位置 */
let sharedViewWindow: SavedViewWindow = {
  spanBars: DEFAULT_RANGE_BARS,
  anchoredRight: true,
  startDate: "",
  endDate: "",
};

/** 在升序日期数组中找到最贴合 saved 视图窗口的 [left, right] 索引范围 */
function resolveViewWindow(
  dates: string[],
  saved: SavedViewWindow,
): { left: number; right: number } {
  const n = dates.length;
  if (n <= 1) return { left: 0, right: Math.max(0, n - 1) };
  if (saved.spanBars === 0) {
    return { left: 0, right: n - 1 };
  }
  const span = Math.max(10, saved.spanBars);
  if (saved.anchoredRight || !saved.startDate || !saved.endDate) {
    return { left: Math.max(0, n - span), right: n - 1 };
  }
  // 历史区间定位：在目标标的的升序日期中查找首个 >= startDate 与末个 <= endDate 的交易日
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (dates[mid] < saved.startDate) lo = mid + 1;
    else hi = mid;
  }
  const mappedLeft = dates[lo] >= saved.startDate ? lo : -1;

  lo = 0;
  hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (dates[mid] <= saved.endDate) lo = mid;
    else hi = mid - 1;
  }
  const mappedRight = dates[lo] <= saved.endDate ? lo : -1;

  if (mappedLeft >= 0 && mappedRight >= mappedLeft && mappedRight - mappedLeft >= 4) {
    return { left: mappedLeft, right: mappedRight };
  }
  // 若目标标的为次新股（上市晚于所选历史区间），回退到最左侧相同跨度；若历史结束更早，回退最右侧相同跨度
  if (dates[0] > saved.endDate) {
    return { left: 0, right: Math.min(n - 1, span - 1) };
  }
  return { left: Math.max(0, n - span), right: n - 1 };
}

function inferPresetRange(
  sIdx: number,
  eIdx: number,
  total: number,
): number {
  if (total <= 0) return DEFAULT_RANGE_BARS;
  if (sIdx <= 0 && eIdx >= total - 1) return 0;
  const anchoredRight = eIdx >= total - 2;
  if (!anchoredRight) return -1;
  const span = eIdx - sIdx + 1;
  for (const preset of [63, 126, 252]) {
    if (Math.abs(span - Math.min(preset, total)) <= 2) {
      return preset;
    }
  }
  return -1;
}

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

/** 根据当前可见时间窗口 [startIdx, endIdx] 计算紧凑的 Y 轴价格范围，消除大片上下空白并防止远期参考线压扁 K 线 */
function computeTightPriceBounds(
  rows: ChartRow[],
  startIdx: number,
  endIdx: number,
  overlay: OverlayMode,
  keyPrices: number[],
): { min: number; max: number } | null {
  if (!rows.length) return null;
  const s = Math.max(0, Math.min(startIdx, rows.length - 1));
  const e = Math.max(s, Math.min(endIdx, rows.length - 1));
  let candleMin = Infinity;
  let candleMax = -Infinity;
  for (let i = s; i <= e; i++) {
    const lo = safeNumber(rows[i].low);
    const hi = safeNumber(rows[i].high);
    const cl = safeNumber(rows[i].close);
    if (lo != null && lo > 0 && lo < candleMin) candleMin = lo;
    if (hi != null && hi > 0 && hi > candleMax) candleMax = hi;
    if (cl != null && cl > 0) {
      if (cl < candleMin) candleMin = cl;
      if (cl > candleMax) candleMax = cl;
    }
  }
  if (!Number.isFinite(candleMin) || !Number.isFinite(candleMax) || candleMax <= 0) {
    return null;
  }
  const baseSpan = Math.max(candleMax - candleMin, candleMax * 0.015);
  let lo = candleMin;
  let hi = candleMax;

  // 仅吸纳紧贴当前可见 K 线的均线/布林与核心防守/突破位，绝不让远期 MA200 或极端目标价拉爆纵轴空白
  const overlayGuardLo = candleMin - baseSpan * 0.12;
  const overlayGuardHi = candleMax + baseSpan * 0.12;
  if (overlay === "MA" || overlay === "BOLL") {
    const fields =
      overlay === "MA" ? ["ma20", "ma50", "ma200"] : ["bb_upper", "bb_lower"];
    for (let i = s; i <= e; i++) {
      for (const f of fields) {
        const v = safeNumber(rows[i][f]);
        if (v != null && v >= overlayGuardLo && v <= overlayGuardHi) {
          if (v < lo) lo = v;
          if (v > hi) hi = v;
        }
      }
    }
  }

  const levelGuardLo = candleMin - baseSpan * 0.18;
  const levelGuardHi = candleMax + baseSpan * 0.18;
  for (const p of keyPrices) {
    if (Number.isFinite(p) && p > 0 && p >= levelGuardLo && p <= levelGuardHi) {
      if (p < lo) lo = p;
      if (p > hi) hi = p;
    }
  }

  const finalSpan = Math.max(hi - lo, candleMax * 0.015);
  const padBottom = finalSpan * 0.07;
  const padTop = finalSpan * 0.08;
  const yMin = Math.max(0, lo - padBottom);
  const yMax = hi + padTop;
  const digits = candleMax < 5 ? 3 : 2;
  return {
    min: Number(yMin.toFixed(digits)),
    max: Number(yMax.toFixed(digits)),
  };
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
  const yBoundsCtxRef = useRef<{
    rows: ChartRow[];
    overlay: OverlayMode;
    keyPrices: number[];
  }>({ rows: [], overlay: "MA", keyPrices: [] });
  const hoverSetter = useRef<(idx: number | null) => void>(() => {});
  const [overlay, setOverlay] = useState<OverlayMode>("MA");
  const [showMacd, setShowMacd] = useState(false);
  const [showRsi, setShowRsi] = useState(false);
  const [showCost, setShowCost] = useState(true);
  const [showForecast, setShowForecast] = useState(true);
  const [showVolumeProfile, setShowVolumeProfile] = useState(true);
  const [showWaveTrend, setShowWaveTrend] = useState(true);
  const [activeRange, setActiveRange] = useState<number>(() =>
    sharedViewWindow.spanBars === 0
      ? 0
      : sharedViewWindow.anchoredRight &&
          (PRESET_RANGES as readonly number[]).includes(sharedViewWindow.spanBars)
        ? sharedViewWindow.spanBars
        : -1,
  );
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
    let zoomRafId: number | null = null;
    instance.on("datazoom", () => {
      if (zoomRafId != null) cancelAnimationFrame(zoomRafId);
      zoomRafId = requestAnimationFrame(() => {
        if (instance.isDisposed()) return;
        const { rows, overlay: ov, keyPrices } = yBoundsCtxRef.current;
        const liveDates = latestDatesRef.current;
        if (!rows.length) return;
        try {
          const opt: any = instance.getOption();
          const dz = opt?.dataZoom?.[0];
          if (!dz) return;
          let sIdx = 0;
          let eIdx = rows.length - 1;
          if (typeof dz.startValue === "number" && typeof dz.endValue === "number") {
            sIdx = Math.round(dz.startValue);
            eIdx = Math.round(dz.endValue);
          } else if (typeof dz.start === "number" && typeof dz.end === "number") {
            sIdx = Math.round(((rows.length - 1) * dz.start) / 100);
            eIdx = Math.round(((rows.length - 1) * dz.end) / 100);
          }
          sIdx = Math.max(0, Math.min(sIdx, rows.length - 1));
          eIdx = Math.max(sIdx, Math.min(eIdx, rows.length - 1));
          const isAll = sIdx <= 0 && eIdx >= rows.length - 1;
          const anchoredRight = eIdx >= rows.length - 2;
          sharedViewWindow = {
            spanBars: isAll ? 0 : Math.max(10, eIdx - sIdx + 1),
            anchoredRight,
            startDate: liveDates[sIdx] ?? "",
            endDate: liveDates[eIdx] ?? "",
          };
          setActiveRange(inferPresetRange(sIdx, eIdx, rows.length));
          const bounds = computeTightPriceBounds(rows, sIdx, eIdx, ov, keyPrices);
          if (bounds) {
            instance.setOption(
              { yAxis: [{ min: bounds.min, max: bounds.max }] },
              { notMerge: false },
            );
          }
        } catch {
          // 忽略缩放期间瞬态读取异常
        }
      });
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
      if (zoomRafId != null) cancelAnimationFrame(zoomRafId);
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
    const vpRef = detail.stock.forecast?.volume_profile;
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
      flRef?.defense_level ?? null,
      flRef?.breakout_level ?? null,
      vpRef?.available ?? false,
      vpRef?.poc ?? null,
      overlay,
      evalMode,
      evalMode === "live" ? (liveEvalRow?.ma20 ?? null) : null,
      evalMode === "live" ? (liveEvalRow?.rsi ?? null) : null,
      showMacd,
      showRsi,
      showCost,
      showForecast,
      showVolumeProfile,
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

    previousKey.current = key;
    // 切换不同标的或重绘时统一沿用跨股共享的缩放跨度与历史时间位置，绝不强制重置回默认窗口
    const resolved = resolveViewWindow(dates, sharedViewWindow);
    const left = Math.max(0, Math.min(resolved.left, rows.length - 1));
    const right = Math.max(left, Math.min(resolved.right, rows.length - 1));

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
            { kind: "price", top: 24, height: "40%" },
            { kind: "vol", top: "50%", height: "10%" },
            { kind: "macd", top: "66%", height: "11%" },
            { kind: "rsi", top: "82.5%", height: "11%" },
          ]
        : showMacd || showRsi
          ? [
              { kind: "price", top: 26, height: "52%" },
              { kind: "vol", top: "62%", height: "11%" },
              { kind: showMacd ? "macd" : "rsi", top: "79.5%", height: "14%" },
            ]
          : [
              { kind: "price", top: 26, height: "69.5%" },
              { kind: "vol", top: "80%", height: "13.5%" },
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
        label: "计划失效",
        price: detail.stock.long_plan.stop,
        color: down,
        side: "left" as const,
      },
      {
        label: "计划目标",
        price: detail.stock.long_plan.target,
        color: up,
        side: "left" as const,
      },
      {
        label: "持仓成本",
        price: costPrice,
        color: "#e2b857",
        side: "left" as const,
      },
    ]
      .filter(({ price }) => price != null)
      .map(({ label, price, color, side }) => ({
        name: `${label} $${fmt(price, 2)}`,
        yAxis: price as number,
        _side: side,
        lineStyle: { color, width: 1.4, type: "dashed", opacity: 0.85 },
        label: { position: "insideStartTop" as string },
      }));

    const fl = detail.stock.forecast?.levels;
    const vp = detail.stock.forecast?.volume_profile;
    const wt = detail.stock.wave_trend;
    const breakoutColor = dark ? "#60a5fa" : "#1d4ed8";
    const defenseColor = dark ? "#f87171" : "#dc2626";
    const pocColor = dark ? "#fbbf24" : "#d97706";
    const labelBg = dark ? "rgba(17, 23, 32, 0.92)" : "rgba(255, 255, 255, 0.94)";

    // 先算出初始可见 Y 轴范围，便于对所有 markLine 标签进行防重叠智能排布
    const keyPricesForBounds: number[] = [];
    if (showForecast && fl?.available) {
      for (const p of [
        fl.breakout_level,
        fl.defense_level,
        fl.buy_high,
        fl.sell_low,
      ]) {
        if (p != null && Number.isFinite(p) && p > 0) keyPricesForBounds.push(p);
      }
    }
    if (showVolumeProfile && vp?.available && vp.poc != null) {
      keyPricesForBounds.push(vp.poc);
    }
    for (const p of [detail.stock.long_plan.stop, detail.stock.long_plan.target]) {
      if (p != null && Number.isFinite(p) && p > 0) keyPricesForBounds.push(p);
    }
    yBoundsCtxRef.current = {
      rows,
      overlay,
      keyPrices: keyPricesForBounds,
    };
    const initialBounds = computeTightPriceBounds(
      rows,
      left,
      right,
      overlay,
      keyPricesForBounds,
    );
    const ySpan =
      initialBounds && initialBounds.max > initialBounds.min
        ? initialBounds.max - initialBounds.min
        : Math.max(safeNumber(rows[rows.length - 1]?.close) ?? 100, 1) * 0.2;

    // 检测右边缘活跃波浪拐点，若突破/防守标签与末端波浪胶囊同高则自动左移错开
    const recentRightPivots =
      showWaveTrend && wt?.available
        ? (wt.wave.pivots ?? [])
            .map((p) => ({ idx: dates.indexOf(p.date), price: p.price }))
            .filter((p) => p.idx >= rows.length - 16)
        : [];
    const collidesRightPivot = (price: number) =>
      recentRightPivots.some((p) => Math.abs(p.price - price) < ySpan * 0.085);

    const keyLevelLines: any[] = [];
    const forecastAreas: any[] = [];
    if (showForecast && fl?.available) {
      const brk = fl.breakout_level ?? fl.sell_low;
      const def = fl.defense_level ?? fl.stop_loss;
      if (brk != null) {
        const shiftLeft = collidesRightPivot(brk);
        keyLevelLines.push({
          name: `${fl.breakout_confluence ? "▲ 共振突破" : "▲ 突破"} $${fmt(brk, 2)}`,
          yAxis: brk,
          _side: "right",
          lineStyle: {
            color: breakoutColor,
            width: fl.breakout_confluence ? 2.0 : 1.7,
            type: [7, 4],
            opacity: 0.95,
          },
          label: {
            show: true,
            position: "insideEndTop",
            offset: shiftLeft ? [-124, 0] : [0, 0],
            color: breakoutColor,
            backgroundColor: labelBg,
            borderColor: breakoutColor,
            borderWidth: 1,
            fontWeight: 600,
          },
        });
      }
      if (def != null) {
        const shiftLeft = collidesRightPivot(def);
        keyLevelLines.push({
          name: `${fl.defense_confluence ? "▼ 共振防守" : "▼ 防守"} $${fmt(def, 2)}`,
          yAxis: def,
          _side: "right",
          lineStyle: {
            color: defenseColor,
            width: fl.defense_confluence ? 2.0 : 1.7,
            type: [7, 4],
            opacity: 0.95,
          },
          label: {
            show: true,
            position: "insideEndBottom",
            offset: shiftLeft ? [-124, 0] : [0, 0],
            color: defenseColor,
            backgroundColor: labelBg,
            borderColor: defenseColor,
            borderWidth: 1,
            fontWeight: 600,
          },
        });
      }
      // 仅当 ATR 止损位与主要防守位价差超过 1.2% 时补充细虚线，避免重复压线
      if (
        fl.stop_loss != null &&
        def != null &&
        Math.abs(fl.stop_loss - def) / Math.max(def, 1e-6) > 0.012
      ) {
        keyLevelLines.push({
          name: `ATR止损 $${fmt(fl.stop_loss, 2)}`,
          yAxis: fl.stop_loss,
          _side: "left",
          lineStyle: { color: defenseColor, width: 1.1, type: "dotted", opacity: 0.65 },
          label: {
            show: true,
            position: "insideStartBottom",
            color: defenseColor,
            backgroundColor: labelBg,
            borderColor: gridColor,
            borderWidth: 1,
          },
        });
      }

      // 用柔和半透明色带表现买区与卖区，替代原先 4 条碎横线，主图更清爽直观
      if (fl.buy_low != null && fl.buy_high != null && fl.buy_high > fl.buy_low) {
        forecastAreas.push([
          {
            name: `买区 $${fmt(fl.buy_low, 2)}–$${fmt(fl.buy_high, 2)}`,
            yAxis: fl.buy_low,
            itemStyle: {
              color: dark ? "rgba(16, 185, 129, 0.11)" : "rgba(16, 185, 129, 0.085)",
              borderColor: dark ? "rgba(52, 211, 153, 0.28)" : "rgba(16, 185, 129, 0.25)",
              borderWidth: 0.8,
              borderType: "dashed",
            },
            label: {
              show: true,
              position: "insideLeft",
              color: dark ? "#34d399" : "#047857",
              fontSize: 12,
              fontWeight: 500,
              padding: [1, 6],
            },
          },
          { yAxis: fl.buy_high },
        ]);
      }
      if (fl.sell_low != null && fl.sell_high != null && fl.sell_high > fl.sell_low) {
        forecastAreas.push([
          {
            name: `卖区 $${fmt(fl.sell_low, 2)}–$${fmt(fl.sell_high, 2)}`,
            yAxis: fl.sell_low,
            itemStyle: {
              color: dark ? "rgba(59, 130, 246, 0.11)" : "rgba(30, 64, 175, 0.065)",
              borderColor: dark ? "rgba(96, 165, 250, 0.28)" : "rgba(30, 64, 175, 0.22)",
              borderWidth: 0.8,
              borderType: "dashed",
            },
            label: {
              show: true,
              position: "insideLeft",
              color: dark ? "#93c5fd" : "#1e40af",
              fontSize: 12,
              fontWeight: 500,
              padding: [1, 6],
            },
          },
          { yAxis: fl.sell_high },
        ]);
      }
    }

    if (showVolumeProfile && vp?.available && vp.poc != null) {
      // 筹码峰 POC 置于中段顶部，天然避开左侧「买区/卖区/计划线」与右侧「突破/防守/波浪」
      keyLevelLines.push({
        name: `筹码峰POC $${fmt(vp.poc, 2)}`,
        yAxis: vp.poc,
        _side: "middle",
        lineStyle: { color: pocColor, width: 1.25, type: "dotted", opacity: 0.85 },
        label: {
          show: true,
          position: "insideMiddleTop",
          color: pocColor,
          backgroundColor: labelBg,
          borderColor: dark ? "rgba(251, 191, 36, 0.45)" : "rgba(217, 119, 6, 0.4)",
          borderWidth: 1,
        },
      });
    }

    // 左侧 markLine 防重叠调度：相邻价差 < 7% 纵轴高度时自动水平错位，杜绝「持仓成本 / 计划失效」压字
    const allRawLines = [...planLines, ...keyLevelLines];
    const leftGroup = allRawLines
      .filter((item) => item._side === "left" && typeof item.yAxis === "number")
      .sort((a, b) => b.yAxis - a.yAxis);
    let prevLeftY: number | null = null;
    let leftStagger = 0;
    for (const item of leftGroup) {
      if (prevLeftY != null && Math.abs(prevLeftY - item.yAxis) < ySpan * 0.075) {
        leftStagger = (leftStagger + 1) % 3;
        if (leftStagger === 1) {
          item.label = { ...item.label, position: "insideStartBottom", offset: [112, 0] };
        } else if (leftStagger === 2) {
          item.label = { ...item.label, position: "insideMiddleBottom" };
        }
      } else {
        leftStagger = 0;
      }
      prevLeftY = item.yAxis;
    }

    const markLines = allRawLines.map(({ _side, ...rest }) => rest);

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
        z: 3,
        data: candleData,
        markLine: {
          silent: true,
          symbol: "none",
          label: {
            position: "insideStartTop",
            formatter: "{b}",
            color: dark ? "#edf2f7" : "#0f172a",
            backgroundColor: labelBg,
            borderColor: gridColor,
            borderWidth: 1,
            borderRadius: 4,
            padding: [2, 6],
            fontSize: 12,
          },
          data: markLines,
        },
        markArea: forecastAreas.length
          ? {
              silent: true,
              data: forecastAreas,
            }
          : undefined,
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

    // 右侧内嵌 126 日筹码分布直方图（低透明背景层，绝不遮挡 K 线或撑开坐标轴）
    if (showVolumeProfile && vp?.available && vp.bins?.length) {
      const vpData = vp.bins.map((b, idx) => [
        idx,
        b.price_low,
        b.price_high,
        b.ratio,
        b.is_poc ? 1 : 0,
        b.in_value_area ? 1 : 0,
      ]);
      const pocBarFill = dark
        ? "rgba(251, 191, 36, 0.34)"
        : "rgba(217, 119, 6, 0.30)";
      const vaBarFill = dark
        ? "rgba(96, 165, 250, 0.18)"
        : "rgba(30, 64, 175, 0.13)";
      const outBarFill = dark
        ? "rgba(148, 163, 184, 0.10)"
        : "rgba(100, 116, 139, 0.09)";
      series.push({
        id: "volume-profile",
        name: "筹码分布",
        type: "custom",
        xAxisIndex: 0,
        yAxisIndex: 0,
        encode: { x: -1, y: -1 },
        silent: true,
        clip: true,
        z: 1,
        animation: false,
        data: vpData,
        renderItem: (params: any, api: any) => {
          const pLow = api.value(1);
          const pHigh = api.value(2);
          const ratio = api.value(3);
          const isPoc = api.value(4) === 1;
          const inVa = api.value(5) === 1;
          const cs = params.coordSys;
          if (!cs || !Number.isFinite(pLow) || !Number.isFinite(pHigh)) {
            return null;
          }
          const ptLow = api.coord([0, pLow]);
          const ptHigh = api.coord([0, pHigh]);
          if (!ptLow || !ptHigh) return null;
          const topY = Math.min(ptHigh[1], ptLow[1]);
          const barH = Math.max(1.5, Math.abs(ptLow[1] - ptHigh[1]) - 1);
          const maxW = Math.min(cs.width * 0.16, 120);
          const barW = Math.max(2, Number(ratio) * maxW);
          const rect = echarts.graphic.clipRectByRect(
            {
              x: cs.x + cs.width - barW,
              y: topY + 0.5,
              width: barW,
              height: barH,
            },
            {
              x: cs.x,
              y: cs.y,
              width: cs.width,
              height: cs.height,
            },
          );
          if (!rect) return null;
          return {
            type: "rect",
            shape: { ...rect, r: [2, 0, 0, 2] },
            style: {
              fill: isPoc ? pocBarFill : inVa ? vaBarFill : outBarFill,
            },
          };
        },
      });
    }

    // Elliott Wave & Parallel Trend Channel overlay (strictly causal backend coordinates)
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
          const nearLeftEdge = idx <= left + 12;
          const nearRightEdge = idx >= rows.length - 10;
          const bucket = isHigh ? shownSameKindIndices.H : shownSameKindIndices.L;
          let labelPos: string = isHigh ? "top" : "bottom";
          let labelDist = 5;
          if (showLabel) {
            const nearCount = bucket.filter((prevIdx) => Math.abs(idx - prevIdx) <= 28).length;
            if (nearCount > 0) {
              // 相邻同侧拐点错开左右与距离，防止带价格胶囊重叠；靠边缘拐点保持贴边对齐防裁字
              labelPos = nearRightEdge || nearLeftEdge
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
              labelDist = 5 + nearCount * 14;
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
              align: nearRightEdge ? "right" : nearLeftEdge ? "left" : undefined,
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
        boundaryGap: undefined,
        min:
          p.kind === "rsi" || p.kind === "vol"
            ? 0
            : p.kind === "price" && initialBounds
              ? initialBounds.min
              : undefined,
        max:
          p.kind === "rsi"
            ? 100
            : p.kind === "price" && initialBounds
              ? initialBounds.max
              : undefined,
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
    showVolumeProfile,
    showWaveTrend,
    theme,
    reverse,
    retrySeq,
  ]);

  const paneTitles = useMemo(() => {
    if (showMacd && showRsi) {
      return [
        { label: "日线价格 / 美元", top: "2px", isPrice: true },
        { label: "成交量 / 股", top: "46%", isPrice: false },
        { label: "MACD (12, 26, 9)", top: "62%", isPrice: false },
        { label: "RSI (14)", top: "78.5%", isPrice: false },
      ];
    }
    if (showMacd || showRsi) {
      return [
        { label: "日线价格 / 美元", top: "2px", isPrice: true },
        { label: "成交量 / 股", top: "58%", isPrice: false },
        {
          label: showMacd ? "MACD (12, 26, 9)" : "RSI (14)",
          top: "75.5%",
          isPrice: false,
        },
      ];
    }
    return [
      { label: "日线价格 / 美元", top: "2px", isPrice: true },
      { label: "成交量 / 股", top: "75.8%", isPrice: false },
    ];
  }, [showMacd, showRsi]);

  const activeWaveTrend = detail?.stock?.wave_trend;

  const zoomTo = (countLimit: number) => {
    const count = displayRows.length;
    const instance = chart.current;
    if (!count || !instance || instance.isDisposed()) return;
    setActiveRange(countLimit);
    const startValue = countLimit ? Math.max(0, count - countLimit) : 0;
    const endValue = count - 1;
    sharedViewWindow = {
      spanBars: countLimit,
      anchoredRight: true,
      startDate: dates[startValue] ?? "",
      endDate: dates[endValue] ?? "",
    };
    try {
      instance.dispatchAction({
        type: "dataZoom",
        startValue,
        endValue,
      });
      const { rows, overlay: ov, keyPrices } = yBoundsCtxRef.current;
      const bounds = computeTightPriceBounds(rows, startValue, endValue, ov, keyPrices);
      if (bounds) {
        instance.setOption(
          { yAxis: [{ min: bounds.min, max: bounds.max }] },
          { notMerge: false },
        );
      }
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
              [63, "近3月", "查看近3个月日线（回到最新）"],
              [126, "近6月", "查看近6个月日线（回到最新）"],
              [252, "近1年", "查看近1年日线（回到最新）"],
              [0, "全部", "查看全部历史日线"],
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
            title="显示或隐藏 MACD 副图（默认关闭，留出更大主图视野）"
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
              title="显示/隐藏主要突破位、防守位及买卖点参考色带"
            >
              点位
            </button>
          )}
          {detail?.stock?.forecast?.volume_profile?.available && (
            <button
              type="button"
              className={showVolumeProfile ? "active" : ""}
              onClick={() => setShowVolumeProfile(!showVolumeProfile)}
              title="显示/隐藏右侧 126 日筹码分布直方图与主筹码峰（POC）"
            >
              筹码
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
