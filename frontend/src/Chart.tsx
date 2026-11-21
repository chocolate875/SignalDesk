import { useEffect, useMemo, useRef, useState } from "react";
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
import { Maximize2, Minimize2 } from "lucide-react";
import type { ChartRow, Detail, WavePivot } from "./types";
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

function formatVolume(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v >= 1_000_000_000) {
    const val = v / 1_000_000_000;
    return val.toFixed(val >= 100 ? 1 : 2) + "B";
  }
  if (v >= 1_000_000) {
    const val = v / 1_000_000;
    return val.toFixed(val >= 100 ? 1 : 2) + "M";
  }
  if (v >= 1_000) return (v / 1_000).toFixed(1) + "K";
  return v.toFixed(0);
}

function OhlcHud({
  rows,
  dates,
  overlay,
  theme,
  registerHover,
}: {
  rows: ChartRow[];
  dates: string[];
  overlay: OverlayMode;
  theme: string;
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
    hoverIdx != null && hoverIdx >= 0 && hoverIdx < rows.length
      ? hoverIdx
      : rows.length - 1;
  const row = rows[idx];
  const prev = idx > 0 ? rows[idx - 1] : null;
  const close = row.close == null ? null : Number(row.close);
  const open = row.open == null ? null : Number(row.open);
  const prevClose = prev?.close == null ? null : Number(prev.close);
  const chgPct =
    close != null && prevClose
      ? ((close / prevClose - 1) * 100)
      : row.return_1 != null
        ? Number(row.return_1) * 100
        : null;
  const isUp =
    chgPct != null
      ? chgPct >= 0
      : close != null && open != null
        ? close >= open
        : true;
  const dirClass = isUp ? "quote-up" : "quote-down";

  return (
    <div className="ohlc-hud" aria-live="off">
      <span className="hud-date">{dates[idx] ?? "—"}</span>
      <span>
        开<b>{fmt(row.open as number, 2)}</b>
      </span>
      <span>
        高<b>{fmt(row.high as number, 2)}</b>
      </span>
      <span>
        低<b>{fmt(row.low as number, 2)}</b>
      </span>
      <span>
        收<b className={dirClass}>{fmt(close, 2)}</b>
      </span>
      <span className={dirClass}>
        {chgPct != null
          ? `${chgPct >= 0 ? "+" : ""}${fmt(chgPct, 2)}%`
          : "—"}
      </span>
      <span>
        量<b>{formatVolume(row.volume as number)}</b>
      </span>
      {overlay === "MA" && (
        <span className="hud-ma">
          <span className="hud-ma-item">
            <i style={{ background: theme === "dark" ? "#e2b857" : "#d97706" }} />
            MA20 {fmt(row.ma20 as number, 2)}
          </span>
          <span className="hud-ma-item">
            <i style={{ background: theme === "dark" ? "#9e9cf2" : "#1e40af" }} />
            MA50 {fmt(row.ma50 as number, 2)}
          </span>
          <span className="hud-ma-item">
            <i style={{ background: theme === "dark" ? "#5cb8e6" : "#64748b" }} />
            MA200 {fmt(row.ma200 as number, 2)}
          </span>
        </span>
      )}
      {overlay === "BOLL" && (
        <span className="hud-ma">
          <span className="hud-ma-item">
            <i style={{ background: theme === "dark" ? "#858ee7" : "#1e40af" }} />
            上 {fmt(row.bb_upper as number, 2)}
          </span>
          <span className="hud-ma-item">
            <i style={{ background: theme === "dark" ? "#e2b857" : "#d97706" }} />
            中 {fmt(row.bb_middle as number, 2)}
          </span>
          <span className="hud-ma-item">
            <i style={{ background: theme === "dark" ? "#858ee7" : "#1e40af" }} />
            下 {fmt(row.bb_lower as number, 2)}
          </span>
        </span>
      )}
    </div>
  );
}

export default function Chart({
  detail,
  theme,
  reverse,
}: {
  detail: Detail | null;
  theme: string;
  reverse: boolean;
}) {
  const root = useRef<HTMLDivElement>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const previousKey = useRef("");
  const hoverSetter = useRef<(idx: number | null) => void>(() => {});
  const [overlay, setOverlay] = useState<OverlayMode>("MA");
  const [showMacd, setShowMacd] = useState(true);
  const [showRsi, setShowRsi] = useState(false);
  const [showCost, setShowCost] = useState(true);
  const [showForecast, setShowForecast] = useState(true);
  const [showWaveTrend, setShowWaveTrend] = useState(true);
  const [activeRange, setActiveRange] = useState<number>(252);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const registerHover = useMemo(
    () => (setter: (idx: number | null) => void) => {
      hoverSetter.current = setter;
    },
    [],
  );

  const dates = useMemo(() => {
    if (!detail?.rows.length) return [];
    const dateFormat = new Intl.DateTimeFormat("sv-SE", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    return detail.rows.map((r) => dateFormat.format(new Date(r.timestamp)));
  }, [detail?.rows]);

  useEffect(() => {
    hoverSetter.current(null);
  }, [detail?.stock.symbol, detail?.mode]);

  useEffect(() => {
    const onFs = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFs);
    return () => document.removeEventListener("fullscreenchange", onFs);
  }, []);

  useEffect(() => {
    if (!root.current) return;
    const instance = echarts.init(root.current, undefined, {
      renderer: "canvas",
    });
    chart.current = instance;
    instance.on("updateAxisPointer", (event: any) => {
      const idx = event?.axesInfo?.[0]?.value;
      hoverSetter.current(typeof idx === "number" ? idx : null);
    });
    instance.on("globalout", () => {
      hoverSetter.current(null);
    });
    const resize = new ResizeObserver(() => instance.resize());
    resize.observe(root.current);
    return () => {
      resize.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    const instance = chart.current;
    if (!instance) return;
    if (!detail?.rows.length) {
      instance.clear();
      previousKey.current = "";
      return;
    }
    const rows = detail.rows;
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
      detail.stock.symbol,
      detail.mode,
      detail.timeframe,
      detail.session,
    ].join("/");
    const old = instance.getOption() as any;
    const zoom =
      key === previousKey.current && old?.xAxis?.[0]?.data?.length
        ? old?.dataZoom?.[0]
        : null;
    previousKey.current = key;

    let left = Math.max(0, rows.length - 252);
    let right = rows.length - 1;
    if (zoom) {
      const oldDates: string[] = old.xAxis[0].data;
      const oldLeft = Math.round(((oldDates.length - 1) * zoom.start) / 100);
      const oldRight = Math.round(((oldDates.length - 1) * zoom.end) / 100);
      if (oldRight >= oldDates.length - 1) {
        left = Math.max(0, right - (oldRight - oldLeft));
      } else {
        const mappedLeft = dates.indexOf(oldDates[oldLeft]);
        const mappedRight = dates.indexOf(oldDates[oldRight]);
        if (mappedLeft >= 0) left = mappedLeft;
        if (mappedRight >= 0) right = Math.max(left, mappedRight);
      }
    }

    const val = (field: string) =>
      rows.map((r) => (r[field] == null ? null : Number(r[field])));
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
            { kind: "price", top: 32, height: "45%" },
            { kind: "vol", top: "55%", height: "10%" },
            { kind: "macd", top: "69%", height: "12%" },
            { kind: "rsi", top: "84%", height: "10%" },
          ]
        : showMacd || showRsi
          ? [
              { kind: "price", top: 32, height: "58%" },
              { kind: "vol", top: "68%", height: "11%" },
              { kind: showMacd ? "macd" : "rsi", top: "82%", height: "14%" },
            ]
          : [
              { kind: "price", top: 32, height: "72%" },
              { kind: "vol", top: "81%", height: "14%" },
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
        data: rows.map((r) => [r.open, r.close, r.low, r.high]),
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
        data: rows.map((r) => ({
          value: r.volume,
          itemStyle: {
            color:
              Number(r.close) >= Number(r.open) ? up + "99" : down + "99",
          },
        })),
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
          if (p.wave_label) {
            if (p.wave_label === "0") return "起";
            return `${p.wave_label}浪${suffix}`;
          }
          return `${shortStruct[p.structure] ?? p.structure}${suffix}`;
        };

        const hasAnyWave = mappedPivots.some((m) => Boolean(m.pivot.wave_label));
        const structCutoff = Math.max(0, mappedPivots.length - (hasAnyWave ? 3 : 5));
        const scatterData = mappedPivots.map(({ idx, pivot }, mIdx) => {
          const hasWave = Boolean(pivot.wave_label);
          const showLabel = hasWave || mIdx >= structCutoff;
          const isHigh = pivot.kind === "H";
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
              position: isHigh ? "top" : "bottom",
              distance: 5,
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
          labelLayout: { hideOverlap: true },
          silent: true,
          animation: false,
        });
      }
    }

    if (macdIdx >= 0) {
      series.push(
        {
          id: "hist",
          name: "MACD柱",
          type: "bar",
          xAxisIndex: macdIdx,
          yAxisIndex: macdIdx,
          data: rows.map((r) => ({
            value: r.macd_hist,
            itemStyle: { color: Number(r.macd_hist) >= 0 ? up : down },
          })),
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
        axisPointer: { type: "cross" },
        confine: true,
        renderMode: "html",
        formatter: (items: { dataIndex: number }[]) => {
          const i = items[0]?.dataIndex;
          const row = rows[i];
          if (!row) return "";
          const value = (field: string, digits = 2) =>
            fmt(row[field] == null ? null : Number(row[field]), digits);
          const lines = [
            `<b>${dates[i]}</b> · 纽约收盘`,
            `开 ${value("open")} · 高 ${value("high")} · 低 ${value("low")} · 收 ${value("close")}`,
            `成交量 ${formatVolume(row.volume as number)} · 成交额 $${formatVolume(row.turnover as number)}`,
            `RSI14 ${value("rsi")} · MACD柱 ${value("macd_hist", 3)}`,
          ];
          const pv = pivotByIndex.get(i);
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
        right: 68,
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
        axisPointer: { show: true },
      })),
      yAxis: panes.map((p, i) => ({
        scale: true,
        gridIndex: i,
        position: "right",
        splitNumber: p.kind === "price" ? 5 : 2,
        boundaryGap: p.kind === "price" ? ["10%", "12%"] : undefined,
        min: p.kind === "rsi" ? 0 : undefined,
        max: p.kind === "rsi" ? 100 : undefined,
        splitLine: {
          show: true,
          lineStyle: { color: gridColor, type: "dashed" },
        },
        axisLabel: {
          color: axis,
          fontSize: 12,
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
          startValue: dates[left],
          endValue: dates[right],
        },
      ],
      series,
    };
    instance.setOption(option, { notMerge: true });
  }, [
    detail,
    dates,
    overlay,
    showMacd,
    showRsi,
    showCost,
    showForecast,
    showWaveTrend,
    theme,
    reverse,
  ]);

  const paneTitles = useMemo(() => {
    if (showMacd && showRsi) {
      return [
        { label: "日线价格 / 美元", top: "4px", isPrice: true },
        { label: "成交量 / 股", top: "51.5%", isPrice: false },
        { label: "MACD (12, 26, 9)", top: "65.5%", isPrice: false },
        { label: "RSI (14)", top: "80.5%", isPrice: false },
      ];
    }
    if (showMacd || showRsi) {
      return [
        { label: "日线价格 / 美元", top: "4px", isPrice: true },
        { label: "成交量 / 股", top: "64.5%", isPrice: false },
        {
          label: showMacd ? "MACD (12, 26, 9)" : "RSI (14)",
          top: "78.5%",
          isPrice: false,
        },
      ];
    }
    return [
      { label: "日线价格 / 美元", top: "4px", isPrice: true },
      { label: "成交量 / 股", top: "77.5%", isPrice: false },
    ];
  }, [showMacd, showRsi]);

  const activeWaveTrend = detail?.stock.wave_trend;

  const zoomTo = (countLimit: number) => {
    const count = detail?.rows.length ?? 0;
    if (!count) return;
    setActiveRange(countLimit);
    chart.current?.dispatchAction({
      type: "dataZoom",
      startValue: countLimit ? Math.max(0, count - countLimit) : 0,
      endValue: count - 1,
    });
  };

  return (
    <div ref={wrapper} className="chart-wrap">
      <div className="chart-toolbar">
        {isFullscreen && detail && (
          <div className="fullscreen-chart-title">
            <b>{ticker(detail.stock.symbol)} · 日线</b>
            <span>
              {detail.mode === "demo" ? "合成行情" : "常规时段 · 不复权"}
            </span>
            <span>
              收盘 ${fmt(detail.summary?.close, 2)} ·{" "}
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
              disabled={!detail?.rows.length}
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
          {(detail?.stock.broker_quantity ?? 0) > 0 &&
            detail?.stock.cost_price != null && (
              <button
                type="button"
                className={showCost ? "active" : ""}
                onClick={() => setShowCost(!showCost)}
                title="显示/隐藏成本线"
              >
                成本
              </button>
            )}
          {detail?.stock.forecast?.levels.available && (
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

        <button
          type="button"
          className="toolbar-fs-btn"
          onClick={() =>
            document.fullscreenElement
              ? document.exitFullscreen()
              : wrapper.current?.requestFullscreen()
          }
          title={isFullscreen ? "退出全屏" : "全屏看图"}
        >
          {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          <span>{isFullscreen ? "退出全屏" : "全屏"}</span>
        </button>
      </div>

      <OhlcHud
        rows={detail?.rows ?? []}
        dates={dates}
        overlay={overlay}
        theme={theme}
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
                  <em
                    className={`chart-wt-pill tone-${activeWaveTrend.trend.tone}`}
                  >
                    {activeWaveTrend.trend.label} ·{" "}
                    {activeWaveTrend.wave.current_wave} ·{" "}
                    {activeWaveTrend.trend.channel_position_label}
                    {activeWaveTrend.trend.invalidation_level != null
                      ? ` · 防守 $${fmt(activeWaveTrend.trend.invalidation_level, 2)}`
                      : ""}
                  </em>
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
        {!detail?.rows.length && (
          <div className="chart-empty">
            该股票日线历史尚未就绪，正在等待有效行情
          </div>
        )}
      </div>
    </div>
  );
}
