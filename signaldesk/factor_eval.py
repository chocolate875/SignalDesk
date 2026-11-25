"""Phase 0 因果因子实证评测工具（只读读取前复权 K 线，输出 RankIC、共线性矩阵与移动止损对比）。

严格遵守：
1. 仅使用截至 t 日已确认常规日线评估 t+5 / t+20 / t+60 表现，零未来数据泄露；
2. CLI 默认仅以只读 URI 访问本地 SQLite 的 bars 表（live-fwd-v3 / macro-live-fwd-v3），绝不触碰任何账户持仓表。
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import AverageTrueRange

from . import operators as op
from .calendar import NY
from .demo import DEMO_NAMES, make_bars
from .factors import _contiguous_regular_tail, compute_yang_zhang_hv
from .indicators import RULE_VERSION
from .instruments import classify_instrument
from .security import data_directory

FACTOR_LABELS: dict[str, str] = {
    "rsi14": "旧: RSI(14)",
    "macd_hist_atr": "旧: MACD柱/ATR",
    "zscore20": "旧: 20日 Z-score",
    "rank20": "旧: 20日时序分位",
    "corr20": "旧: 20日量价相关",
    "volume_v1_1d": "旧: 单日量价分",
    "volume_v2_flow10": "新: 10日平滑量价",
    "residual_mom_z": "新: 残差动量(vs SPY)",
    "high_52w_ratio": "新: 52周高点锚定",
    "neg_info_discreteness": "新: 趋势连续度(-ID)",
    "overnight_20d_pct": "新: 20日隔夜动量",
    "neg_max5_21d": "新: 低彩票效应(-MAX5)",
    "neg_downside_beta": "新: 低大盘下行Beta",
    "neg_yang_zhang_hv60": "新: 低Yang-Zhang波动",
    "neg_amihud_20d": "新: 高流动性(-Amihud)",
}


def _clean_regular_frame(bars: list[dict]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame(bars).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"])
    if "confirmed" in df.columns:
        df = df[df["confirmed"]]
    df = df.sort_values("timestamp", kind="stable").drop_duplicates("timestamp", keep="last")
    tail = _contiguous_regular_tail(df)
    if tail.empty:
        return pd.DataFrame()
    ts = pd.to_datetime(tail["timestamp"], utc=True)
    tail["ny_date"] = ts.dt.tz_convert(NY).map(lambda t: (t.to_pydatetime() + timedelta(hours=4)).date())
    return tail.reset_index(drop=True)


def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    mask = np.isfinite(x) & np.isfinite(y)
    if int(mask.sum()) < 5:
        return None
    sx = pd.Series(x[mask]).rank(method="average")
    sy = pd.Series(y[mask]).rank(method="average")
    if sx.std(ddof=0) <= 1e-12 or sy.std(ddof=0) <= 1e-12:
        return None
    val = float(sx.corr(sy))
    return val if math.isfinite(val) else None


def _simulate_trailing_stop_window(
    closes: np.ndarray,
    t: int,
    horizon: int,
    atr_t: float,
) -> tuple[float, float, float, float]:
    """返回 (固定持有收益, 固定持有最大回撤, 移动止损收益, 移动止损最大回撤)。"""
    p0 = closes[t]
    path = closes[t + 1 : t + 1 + horizon]
    # 固定持有曲线（以 1.0 为净值起点）
    eq_bh = path / p0
    peak_bh = np.maximum.accumulate(np.insert(eq_bh, 0, 1.0))[1:]
    dd_bh = float(np.min(eq_bh / peak_bh - 1.0))
    ret_bh = float(eq_bh[-1] - 1.0)

    # 2.5 × ATR 动态峰值移动止损
    run_peak = p0
    stop_dist = 2.5 * atr_t
    eq_ts = np.empty(len(path), dtype=float)
    stopped = False
    locked_eq = 1.0
    for idx, price in enumerate(path):
        if stopped:
            eq_ts[idx] = locked_eq
            continue
        stop_line = run_peak - stop_dist
        if price <= stop_line:
            stopped = True
            locked_eq = price / p0
            eq_ts[idx] = locked_eq
        else:
            eq_ts[idx] = price / p0
            if price > run_peak:
                run_peak = price
    peak_ts = np.maximum.accumulate(np.insert(eq_ts, 0, 1.0))[1:]
    dd_ts = float(np.min(eq_ts / peak_ts - 1.0))
    ret_ts = float(eq_ts[-1] - 1.0)
    return ret_bh, dd_bh, ret_ts, dd_ts


def _skewness(arr: np.ndarray) -> float | None:
    if len(arr) < 10:
        return None
    mu = float(np.mean(arr))
    sd = float(np.std(arr, ddof=0))
    if sd <= 1e-12:
        return None
    return round(float(np.mean(((arr - mu) / sd) ** 3)), 3)


def evaluate_factor_panel(
    bars_by_symbol: dict[str, list[dict]],
    spy_bars: list[dict] | None = None,
    step: int = 5,
) -> dict[str, Any]:
    """对多标的已确认前复权日线执行严格因果截面 RankIC、共线性与移动止损评测。"""
    spy_df = _clean_regular_frame(spy_bars) if spy_bars else pd.DataFrame()
    spy_ret_map: dict[Any, float] = {}
    if len(spy_df) >= 2:
        spy_c = spy_df["close"].to_numpy(dtype=float)
        spy_r = np.diff(spy_c) / spy_c[:-1]
        for d, r in zip(spy_df["ny_date"].iloc[1:], spy_r):
            if math.isfinite(float(r)):
                spy_ret_map[d] = float(r)

    rows: list[dict[str, Any]] = []
    stop_records_20: list[tuple[float, float, float, float]] = []
    stop_records_60: list[tuple[float, float, float, float]] = []
    included_symbols: list[str] = []
    skipped_leveraged: list[str] = []

    for sym, raw_bars in sorted(bars_by_symbol.items()):
        # This SPY-based cross section uses one market closing time and USD turnover.
        if not sym.endswith(".US"):
            continue
        inst = classify_instrument(sym)
        if inst.get("is_leveraged"):
            skipped_leveraged.append(sym)
            continue
        df = _clean_regular_frame(raw_bars)
        if len(df) < 280:
            continue
        included_symbols.append(sym)

        c = df["close"].astype(float)
        h = df["high"].astype(float)
        low = df["low"].astype(float)
        o = df["open"].astype(float)
        v = df["volume"].astype(float)
        t_series = df["turnover"].astype(float) if "turnover" in df.columns else (c * v)

        rsi14 = RSIIndicator(c, 14, fillna=False).rsi().to_numpy(dtype=float)
        macd_hist = MACD(c, 26, 12, 9, fillna=False).macd_diff().to_numpy(dtype=float)
        atr = AverageTrueRange(h, low, c, 14, fillna=False).average_true_range()
        atr = atr.where(np.arange(len(df)) >= 13).replace(0, np.nan).to_numpy(dtype=float)

        rvol = (v / op.mean(op.delay(v), 20).replace(0, np.nan)).to_numpy(dtype=float)
        ret_s = op.returns(c, 1)
        vol_v1 = (np.sign(ret_s) * op.clip(pd.Series(rvol) - 1, 0, 1)).to_numpy(dtype=float)

        atr_pct = (pd.Series(atr) / c).replace(0, np.nan)
        signed_flow = op.clip(ret_s / atr_pct, -1, 1) * op.clip(pd.Series(rvol), 0.5, 2.5)
        flow_den = op.mean(signed_flow.abs(), 10).replace(0, np.nan)
        vol_v2 = op.clip(op.mean(signed_flow, 10) / flow_den, -1, 1).fillna(0.0).to_numpy(dtype=float)

        zs20 = op.zscore(c, 20).to_numpy(dtype=float)
        rk20 = op.ts_rank(c, 20).to_numpy(dtype=float)
        cr20 = op.corr(ret_s, op.delta(v), 20).to_numpy(dtype=float)

        closes = c.to_numpy(dtype=float)
        highs = h.to_numpy(dtype=float)
        lows = low.to_numpy(dtype=float)
        opens = o.to_numpy(dtype=float)
        dates = df["ny_date"].tolist()
        turns = np.where(np.isfinite(t_series.to_numpy()) & (t_series.to_numpy() > 0), t_series.to_numpy(), ((highs + lows + closes) / 3.0) * v.to_numpy())

        simple_rets = np.empty(len(closes), dtype=float)
        simple_rets[0] = np.nan
        simple_rets[1:] = np.diff(closes) / closes[:-1]

        sample_count = 0
        for t in range(252, len(df) - 60, step):
            ct = closes[t]
            at = atr[t]
            if not (math.isfinite(ct) and ct > 0 and math.isfinite(at) and at > 0):
                continue

            # 未来收益
            fwd_5 = closes[t + 5] / ct - 1.0
            fwd_20 = closes[t + 20] / ct - 1.0
            fwd_60 = closes[t + 60] / ct - 1.0

            # 历史窗口（严格 <= t）
            win_rets_252 = simple_rets[t - 251 : t + 1]
            win_rets_form = win_rets_252[:-21]
            if not np.isfinite(win_rets_form).all():
                continue

            h52 = float(np.max(highs[t - 251 : t + 1]))
            high_52w_ratio = ct / h52 if h52 > 0 else np.nan

            # FIP / ID
            cum_p = float(np.prod(1.0 + win_rets_form) - 1.0)
            sign_p = 1.0 if cum_p > 0 else (-1.0 if cum_p < 0 else 0.0)
            id_val = sign_p * (float(np.mean(win_rets_form < 0)) - float(np.mean(win_rets_form > 0)))

            # 20日隔夜累计
            g_on_20 = opens[t - 19 : t + 1] / closes[t - 20 : t]
            on_20 = float(np.prod(g_on_20) - 1.0) * 100.0 if np.isfinite(g_on_20).all() else np.nan

            # MAX5
            r21 = simple_rets[t - 20 : t + 1]
            max5 = float(np.mean(np.sort(r21)[-5:]) * 100.0) if np.isfinite(r21).all() else np.nan

            # Yang-Zhang 60日
            yz60 = compute_yang_zhang_hv(
                opens[t - 61 : t + 1],
                highs[t - 61 : t + 1],
                lows[t - 61 : t + 1],
                closes[t - 61 : t + 1],
                60,
            )

            # Amihud 20日
            dv20 = turns[t - 19 : t + 1]
            r20 = simple_rets[t - 19 : t + 1]
            m20 = np.isfinite(dv20) & (dv20 > 0) & np.isfinite(r20)
            amihud = (
                float(np.mean((np.abs(r20[m20]) * 100.0) / (dv20[m20] / 1_000_000.0)))
                if int(m20.sum()) >= 15
                else np.nan
            )

            # 残差动量与下行 Beta（与 SPY 对齐）
            res_mom = np.nan
            dn_beta = np.nan
            if spy_ret_map:
                pairs = [
                    (simple_rets[k], spy_ret_map[dates[k]])
                    for k in range(t - 251, t + 1)
                    if dates[k] in spy_ret_map and math.isfinite(simple_rets[k])
                ]
                if len(pairs) >= 126:
                    arr_p = np.asarray(pairs, dtype=float)
                    ri, rm = arr_p[:, 0], arr_p[:, 1]
                    varm = float(np.var(rm, ddof=1))
                    if varm > 1e-12:
                        beta_est = float(np.cov(ri, rm, ddof=1)[0, 1] / varm)
                        eps_f = ri[:-21] - beta_est * rm[:-21]
                        sd_e = float(np.std(eps_f, ddof=1))
                        if sd_e > 1e-12:
                            res_mom = float(np.sum(eps_f)) / (sd_e * math.sqrt(len(eps_f)))
                    dn_arr = arr_p[-min(len(arr_p), 126) :]
                    dn_mask = dn_arr[:, 1] < 0
                    if int(dn_mask.sum()) >= 15:
                        rm_d, ri_d = dn_arr[dn_mask, 1], dn_arr[dn_mask, 0]
                        vmd = float(np.var(rm_d, ddof=1))
                        if vmd > 1e-12:
                            dn_beta = float(np.cov(ri_d, rm_d, ddof=1)[0, 1] / vmd)

            rows.append(
                {
                    "date": dates[t],
                    "symbol": sym,
                    "fwd_5": fwd_5,
                    "fwd_20": fwd_20,
                    "fwd_60": fwd_60,
                    "rsi14": rsi14[t],
                    "macd_hist_atr": macd_hist[t] / at if math.isfinite(macd_hist[t]) else np.nan,
                    "zscore20": zs20[t],
                    "rank20": rk20[t],
                    "corr20": cr20[t],
                    "volume_v1_1d": vol_v1[t],
                    "volume_v2_flow10": vol_v2[t],
                    "residual_mom_z": res_mom,
                    "high_52w_ratio": high_52w_ratio,
                    "neg_info_discreteness": -id_val,
                    "overnight_20d_pct": on_20,
                    "neg_max5_21d": -max5 if math.isfinite(max5) else np.nan,
                    "neg_downside_beta": -dn_beta if math.isfinite(dn_beta) else np.nan,
                    "neg_yang_zhang_hv60": -float(yz60) if yz60 is not None else np.nan,
                    "neg_amihud_20d": -amihud if math.isfinite(amihud) else np.nan,
                }
            )

            sample_count += 1
            if sample_count % 2 == 1:
                stop_records_20.append(_simulate_trailing_stop_window(closes, t, 20, at))
                stop_records_60.append(_simulate_trailing_stop_window(closes, t, 60, at))

    panel = pd.DataFrame(rows)
    factors = list(FACTOR_LABELS.keys())
    min_cs = 5 if len(included_symbols) < 15 else 15

    ic_results: dict[str, dict[str, Any]] = {}
    if not panel.empty:
        grouped = list(panel.groupby("date"))
        for fname in factors:
            stats_by_h: dict[str, Any] = {}
            for h_key in ("fwd_5", "fwd_20", "fwd_60"):
                ics = []
                for _, sub in grouped:
                    if len(sub) < min_cs:
                        continue
                    ic = _spearman(sub[fname].to_numpy(dtype=float), sub[h_key].to_numpy(dtype=float))
                    if ic is not None:
                        ics.append(ic)
                if ics:
                    arr_ic = np.asarray(ics, dtype=float)
                    mean_ic = float(np.mean(arr_ic))
                    std_ic = float(np.std(arr_ic, ddof=1)) if len(arr_ic) > 1 else 0.0
                    icir = mean_ic / std_ic if std_ic > 1e-12 else 0.0
                    stats_by_h[h_key] = {
                        "mean_ic": round(mean_ic, 4),
                        "icir": round(icir, 3),
                        "n_dates": len(ics),
                    }
                else:
                    stats_by_h[h_key] = {"mean_ic": None, "icir": None, "n_dates": 0}
            ic_results[fname] = {"label": FACTOR_LABELS[fname], **stats_by_h}

    # 平均截面两两相关性矩阵，量化旧指标共线冗余
    corr_sum = np.zeros((len(factors), len(factors)), dtype=float)
    corr_cnt = np.zeros((len(factors), len(factors)), dtype=int)
    if not panel.empty:
        for _, sub in panel.groupby("date"):
            if len(sub) < min_cs:
                continue
            ranked = sub[factors].rank(method="average")
            cmat = ranked.corr().to_numpy(dtype=float)
            valid_c = np.isfinite(cmat)
            corr_sum[valid_c] += cmat[valid_c]
            corr_cnt[valid_c] += 1

    top_collinear: list[dict[str, Any]] = []
    for i in range(len(factors)):
        for j in range(i + 1, len(factors)):
            if corr_cnt[i, j] > 0:
                avg_r = float(corr_sum[i, j] / corr_cnt[i, j])
                top_collinear.append(
                    {
                        "pair": f"{factors[i]} <-> {factors[j]}",
                        "labels": f"{FACTOR_LABELS[factors[i]]} / {FACTOR_LABELS[factors[j]]}",
                        "avg_spearman": round(avg_r, 3),
                        "n_dates": int(corr_cnt[i, j]),
                    }
                )
    top_collinear.sort(key=lambda item: abs(item["avg_spearman"]), reverse=True)

    def _summarize_stops(recs: list[tuple[float, float, float, float]]) -> dict[str, Any]:
        if not recs:
            return {}
        arr = np.asarray(recs, dtype=float)
        return {
            "samples": len(arr),
            "buy_hold_mean_ret_pct": round(float(np.mean(arr[:, 0]) * 100.0), 2),
            "trailing_stop_mean_ret_pct": round(float(np.mean(arr[:, 2]) * 100.0), 2),
            "buy_hold_avg_max_dd_pct": round(float(np.mean(arr[:, 1]) * 100.0), 2),
            "trailing_stop_avg_max_dd_pct": round(float(np.mean(arr[:, 3]) * 100.0), 2),
            "buy_hold_skew": _skewness(arr[:, 0]),
            "trailing_stop_skew": _skewness(arr[:, 2]),
        }

    return {
        "rule_version": RULE_VERSION,
        "market": "US",
        "included_symbols_count": len(included_symbols),
        "skipped_leveraged_count": len(skipped_leveraged),
        "panel_observations": int(len(panel)),
        "min_cross_section": min_cs,
        "factor_ic": ic_results,
        "top_collinear_pairs": top_collinear[:15],
        "trailing_stop_comparison": {
            "20d": _summarize_stops(stop_records_20),
            "60d": _summarize_stops(stop_records_60),
        },
    }


def _load_readonly_bars_from_sqlite(db_path: Path) -> tuple[dict[str, list[dict]], list[dict]]:
    if not db_path.exists():
        return {}, []
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT source, symbol, payload FROM bars WHERE source IN ('live-fwd-v3', 'macro-live-fwd-v3') AND timeframe='day' ORDER BY symbol, timestamp"
        ).fetchall()
    finally:
        con.close()
    bars_by_symbol: dict[str, list[dict]] = {}
    macro_spy_bars: list[dict] = []
    for source, symbol, payload in rows:
        bar = json.loads(payload)
        if source == "live-fwd-v3":
            bars_by_symbol.setdefault(symbol, []).append(bar)
        elif source == "macro-live-fwd-v3" and symbol == "SPY.US":
            macro_spy_bars.append(bar)
    spy_bars = macro_spy_bars or bars_by_symbol.get("SPY.US", [])
    return bars_by_symbol, spy_bars


def main():
    parser = argparse.ArgumentParser(description="SignalDesk Phase 0 因果因子评测工具（只读 bars 表）")
    parser.add_argument("--output", type=Path, help="输出 JSON 报告路径")
    parser.add_argument("--step", type=int, default=5, help="截面采样步长（交易日）")
    args = parser.parse_args()

    db_path = data_directory() / "signaldesk.sqlite3"
    bars_by_symbol, spy_bars = _load_readonly_bars_from_sqlite(db_path)
    dataset_kind = "live-fwd-v3"
    if not bars_by_symbol:
        dataset_kind = "synthetic-demo"
        now = datetime.now(timezone.utc)
        for sym, _, _, _, _, _ in DEMO_NAMES:
            bars_by_symbol[sym] = make_bars(sym, "day", now)
        spy_bars = make_bars("SPY.US", "day", now)

    report = evaluate_factor_panel(bars_by_symbol, spy_bars=spy_bars, step=args.step)
    report["dataset"] = dataset_kind
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
