import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { CandlestickChart, LineChart, BarChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
  MarkLineComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { Detail } from "./types";
echarts.use([
  CandlestickChart,
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  AxisPointerComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export default function Chart({
  detail,
  overlay,
  theme,
  reverse,
}: {
  detail: Detail | null;
  overlay: string;
  theme: string;
  reverse: boolean;
}) {
  const root = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const previousKey = useRef("");
  useEffect(() => {
    if (!root.current) return;
    const instance = echarts.init(root.current, undefined, {
      renderer: "canvas",
    });
    chart.current = instance;
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
    if (!instance || !detail) return;
    const rows = detail.rows;
    if (!rows.length) {
      instance.clear();
      return;
    }
    const dark = theme === "dark";
    const up = reverse ? "#f17e83" : "#68dbb1";
    const down = reverse ? "#68dbb1" : "#ef7d87";
    const axis = dark ? "#69798c" : "#8390a2";
    const grid = dark ? "#1c2735" : "#e8edf4";
    const key = detail.stock.symbol + detail.timeframe + detail.session;
    const old = instance.getOption() as any;
    const zoom = key === previousKey.current ? old.dataZoom?.[0] : null;
    previousKey.current = key;
    const x = rows.map((r) =>
      new Date(r.timestamp).toLocaleString("en-US", {
        timeZone: "America/New_York",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }),
    );
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
      lineStyle: { width: 1.3, color },
      itemStyle: { color },
      animation: false,
    });
    const option: any = {
      animation: false,
      backgroundColor: "transparent",
      textStyle: { fontFamily: "Segoe UI, Microsoft YaHei, sans-serif" },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "cross" },
        confine: true,
        backgroundColor: dark ? "#172331" : "#fff",
        borderColor: grid,
        textStyle: { color: dark ? "#cfdae7" : "#223044", fontSize: 11 },
      },
      axisPointer: {
        link: [{ xAxisIndex: "all" }],
        label: { backgroundColor: "#42546b" },
      },
      grid: [
        { left: 14, right: 58, top: 18, height: "43%" },
        { left: 14, right: 58, top: "51%", height: "10%" },
        { left: 14, right: 58, top: "66%", height: "12%" },
        { left: 14, right: 58, top: "83%", height: "10%" },
      ],
      xAxis: [0, 1, 2, 3].map((i) => ({
        type: "category",
        data: x,
        gridIndex: i,
        boundaryGap: true,
        axisLine: { lineStyle: { color: grid } },
        axisTick: { show: false },
        axisLabel: {
          show: i === 3,
          color: axis,
          fontSize: 10,
          hideOverlap: true,
        },
        splitLine: { show: false },
        axisPointer: { show: true },
      })),
      yAxis: [0, 1, 2, 3].map((i) => ({
        scale: true,
        gridIndex: i,
        position: "right",
        splitNumber: i ? 2 : 4,
        min: i === 3 ? 0 : undefined,
        max: i === 3 ? 100 : undefined,
        splitLine: { show: true, lineStyle: { color: grid, type: "dashed" } },
        axisLabel: {
          color: axis,
          fontSize: 10,
          formatter: (v: number) =>
            i === 1
              ? (v / 1000000).toFixed(1) + "M"
              : i === 3
                ? v.toFixed(0)
                : v.toFixed(2),
        },
        axisLine: { show: false },
        axisTick: { show: false },
      })),
      dataZoom: [
        {
          type: "inside",
          xAxisIndex: [0, 1, 2, 3],
          start: zoom?.start ?? 58,
          end: zoom?.end ?? 100,
        },
      ],
      series: [
        {
          id: "price",
          name: "OHLC",
          type: "candlestick",
          data: rows.map((r) => [r.open, r.close, r.low, r.high]),
          itemStyle: {
            color: up,
            color0: down,
            borderColor: up,
            borderColor0: down,
          },
        },
        line("MA20", "ma20", "#d7b778", 0, overlay === "MA"),
        line("MA50", "ma50", "#9a9ce6", 0, overlay === "MA"),
        line("布林上轨", "bb_upper", "#858ee7", 0, overlay === "BOLL"),
        line("布林中轨", "bb_middle", "#d7b778", 0, overlay === "BOLL"),
        line("布林下轨", "bb_lower", "#858ee7", 0, overlay === "BOLL"),
        line("VWAP", "vwap", "#66b6df", 0, overlay === "VWAP"),
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
                Number(r.close) >= Number(r.open) ? up + "88" : down + "88",
            },
          })),
        },
        {
          id: "hist",
          name: "MACD柱",
          type: "bar",
          xAxisIndex: 2,
          yAxisIndex: 2,
          data: rows.map((r) => ({
            value: r.macd_hist,
            itemStyle: { color: Number(r.macd_hist) >= 0 ? up : down },
          })),
        },
        line("MACD", "macd", "#d7b778", 2),
        line("Signal", "macd_signal", "#9a9ce6", 2),
        {
          ...line("RSI14", "rsi", "#9a9ce6", 3),
          markLine: {
            silent: true,
            symbol: "none",
            label: { show: false },
            lineStyle: { color: axis, type: "dashed", opacity: 0.5 },
            data: [{ yAxis: 30 }, { yAxis: 70 }],
          },
        },
      ],
    };
    instance.setOption(option, { notMerge: false, lazyUpdate: true });
  }, [detail, overlay, theme, reverse]);
  return (
    <div className="chart-wrap">
      <div className="chart-labels">
        <span>PRICE / USD</span>
        <span>VOLUME</span>
        <span>MACD 12 · 26 · 9</span>
        <span>RSI 14</span>
      </div>
      <div
        ref={root}
        className="price-chart"
        role="img"
        aria-label="价格、成交量、MACD与RSI联动图"
      />
      {!detail?.rows.length && (
        <div className="chart-empty">该周期数据尚未就绪，正在等待有效行情</div>
      )}
    </div>
  );
}
