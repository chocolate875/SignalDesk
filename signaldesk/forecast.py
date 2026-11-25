"""Causal buy/sell price level recommendations and 5-tier stock ratings."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .indicators import finite

TIER_SPECS = {
    "strong_buy": ("强烈买入", "positive", 5),
    "buy": ("建议买入", "positive", 4),
    "hold": ("中性观望", "neutral", 3),
    "reduce": ("谨慎减持", "warning", 2),
    "sell": ("建议卖出", "danger", 1),
}
TIER_ORDER = ["sell", "reduce", "hold", "buy", "strong_buy"]
DISCLAIMER = "基于已确认日线、历史波动率与公开估值/利率测算，仅供复核参考，不构成投资建议。"
ETF_DISCLAIMER = "基于已确认日线、历史回撤分位、波动率与美债利率测算（不采用失真的基金主体 PE），仅供复核参考，不构成投资建议。"


def _unavailable_volume_profile(reason: str = "有效成交量日线样本不足，暂不测算筹码分布") -> dict:
    return {
        "available": False,
        "reason": reason,
        "window_days": 0,
        "poc": None,
        "vah": None,
        "val": None,
        "support_hvn": None,
        "support_zone_low": None,
        "resistance_hvn": None,
        "resistance_zone_high": None,
        "lvn_price": None,
        "profit_ratio_pct": None,
        "overhead_supply_pct": None,
        "concentration_pct": None,
        "position_label": "数据待补",
        "bins": [],
    }


def _unavailable_payload(reason: str = "已确认日线窗口或波动率数据不足，暂不生成点位预测") -> dict:
    return {
        "levels": {
            "available": False,
            "reason": reason,
            "buy_low": None,
            "buy_high": None,
            "ideal_buy": None,
            "sell_low": None,
            "sell_high": None,
            "stop_loss": None,
            "defense_level": None,
            "defense_anchor": "",
            "defense_confluence": False,
            "breakout_level": None,
            "breakout_anchor": "",
            "breakout_confluence": False,
            "buy_discount_pct": None,
            "upside_pct": None,
            "target_upside_pct": None,
            "downside_pct": None,
            "risk_reward_ratio": None,
            "entry_risk_reward_ratio": None,
            "position_label": "数据待补",
            "buy_anchors": [],
            "sell_anchors": [],
            "stop_anchor": "",
        },
        "volume_profile": _unavailable_volume_profile(reason),
        "rating": {
            "available": False,
            "code": "unavailable",
            "label": "暂不评级",
            "tone": "muted",
            "score": None,
            "stars": 0,
            "confidence": "低",
            "summary": "有效日线或指标窗口尚未完成，暂不出具买卖评级。",
            "factors": [],
            "guardrails": [],
            "disclaimer": DISCLAIMER,
        },
        "risk_budget": {
            "available": False,
            "yz_hv_pct": None,
            "vol_scale": None,
            "macro_red_count": None,
            "macro_multiplier": None,
            "macro_label": "未同步",
            "suggested_exposure_ratio": None,
            "trailing_stop": None,
            "peak_60d": None,
            "trailing_drawdown_pct": None,
            "trailing_breached": False,
            "note": "",
        },
    }


def compute_volume_profile(
    tail: pd.DataFrame | None,
    atr: float | None = None,
    window: int = 126,
    num_bins: int = 28,
) -> dict:
    """严格因果 126 日滚动成交量筹码分布（Volume Profile），提取 POC、70% 价值区与上下筹码峰。

    算法说明：
    - 仅读取已确认连续常规日线的尾部窗口（默认 126 个交易日 ≈ 近 6 个月，零未来函数）；
    - 每根日线成交量按三角核（峰值落在典型价 `(H + L + 2C) / 4`，两翼覆盖 `[L, H]`）分摊至覆盖的价格桶；
    - 采用 90 个交易日半衰期的温和指数衰减权重，使近期换手筹码更具代表性而不丢弃中期主筹码峰。
    """
    if tail is None or tail.empty or "volume" not in tail.columns:
        return _unavailable_volume_profile()
    seg = tail.tail(max(40, int(window)))
    if len(seg) < 40:
        return _unavailable_volume_profile()

    highs = seg["high"].to_numpy(dtype=float)
    lows = seg["low"].to_numpy(dtype=float)
    closes = seg["close"].to_numpy(dtype=float)
    volumes = seg["volume"].to_numpy(dtype=float)

    valid_vol = np.isfinite(volumes) & (volumes > 0)
    if int(valid_vol.sum()) < 30:
        return _unavailable_volume_profile("有效成交量记录不足，暂不测算筹码分布")

    p_min = float(np.nanmin(lows))
    p_max = float(np.nanmax(highs))
    close_now = float(closes[-1])
    if not (math.isfinite(p_min) and math.isfinite(p_max) and math.isfinite(close_now)) or p_max - p_min <= 1e-6:
        return _unavailable_volume_profile("价格区间缺乏波动，暂不测算筹码分布")

    bins_n = max(12, min(int(num_bins), 48))
    edges = np.linspace(p_min, p_max, bins_n + 1, dtype=float)
    centers = 0.5 * (edges[:-1] + edges[1:])
    bin_w = float(edges[1] - edges[0])

    n = len(seg)
    ages = np.arange(n - 1, -1, -1, dtype=float)
    time_weights = np.power(0.5, ages / 90.0)
    bucket_vols = np.zeros(bins_n, dtype=float)

    for i in range(n):
        vol = volumes[i]
        if not math.isfinite(vol) or vol <= 0:
            continue
        w_vol = float(vol) * float(time_weights[i])
        lo_i = float(lows[i])
        hi_i = float(highs[i])
        cl_i = float(closes[i])
        if hi_i <= lo_i + 1e-9:
            b_idx = int(np.clip((cl_i - p_min) / bin_w, 0, bins_n - 1))
            bucket_vols[b_idx] += w_vol
            continue
        first_bin = max(0, int(math.floor((lo_i - p_min) / bin_w)))
        last_bin = min(bins_n - 1, int(math.floor((hi_i - p_min) / bin_w)))
        if first_bin == last_bin:
            bucket_vols[first_bin] += w_vol
            continue
        tp = (hi_i + lo_i + 2.0 * cl_i) / 4.0
        half_lo = max(tp - lo_i, 1e-6)
        half_hi = max(hi_i - tp, 1e-6)
        weights = np.zeros(last_bin - first_bin + 1, dtype=float)
        for j, b_idx in enumerate(range(first_bin, last_bin + 1)):
            ov_lo = max(lo_i, float(edges[b_idx]))
            ov_hi = min(hi_i, float(edges[b_idx + 1]))
            overlap = max(0.0, ov_hi - ov_lo)
            if overlap <= 0:
                continue
            mid = 0.5 * (ov_lo + ov_hi)
            # 三角密度核：收盘典型价处权重最高，向高低影线末端平滑递减至 0.25 基底
            if mid <= tp:
                density = 0.25 + 0.75 * max(0.0, 1.0 - (tp - mid) / half_lo)
            else:
                density = 0.25 + 0.75 * max(0.0, 1.0 - (mid - tp) / half_hi)
            weights[j] = overlap * density
        w_sum = float(weights.sum())
        if w_sum > 0:
            bucket_vols[first_bin : last_bin + 1] += w_vol * (weights / w_sum)

    total_vol = float(bucket_vols.sum())
    if total_vol <= 0 or not math.isfinite(total_vol):
        return _unavailable_volume_profile("有效筹码累计量为零")

    poc_idx = int(np.argmax(bucket_vols))
    poc_price = round(float(centers[poc_idx]), 2)

    # 70% Value Area（从 POC 向高量侧逐步扩张）
    va_low_idx = poc_idx
    va_high_idx = poc_idx
    va_sum = float(bucket_vols[poc_idx])
    target_va = total_vol * 0.70
    while va_sum < target_va and (va_low_idx > 0 or va_high_idx < bins_n - 1):
        left_v = float(bucket_vols[va_low_idx - 1]) if va_low_idx > 0 else -1.0
        right_v = float(bucket_vols[va_high_idx + 1]) if va_high_idx < bins_n - 1 else -1.0
        if right_v >= left_v and va_high_idx < bins_n - 1:
            va_high_idx += 1
            va_sum += float(bucket_vols[va_high_idx])
        elif va_low_idx > 0:
            va_low_idx -= 1
            va_sum += float(bucket_vols[va_low_idx])
        else:
            break

    val_price = round(float(edges[va_low_idx]), 2)
    vah_price = round(float(edges[va_high_idx + 1]), 2)

    # 现价下方获利筹码占比 & 上方套牢筹码占比
    profit_vol = 0.0
    for idx in range(bins_n):
        b_lo = float(edges[idx])
        b_hi = float(edges[idx + 1])
        if close_now >= b_hi:
            profit_vol += float(bucket_vols[idx])
        elif close_now > b_lo:
            profit_vol += float(bucket_vols[idx]) * ((close_now - b_lo) / max(b_hi - b_lo, 1e-9))
    profit_ratio_pct = round(float(np.clip(profit_vol / total_vol * 100.0, 0.0, 100.0)), 1)
    overhead_supply_pct = round(100.0 - profit_ratio_pct, 1)

    # 轻度 3 点平滑识别局部高量峰（HVN）与低量真空区（LVN）
    kernel = np.array([0.2, 0.6, 0.2], dtype=float)
    padded = np.pad(bucket_vols, (1, 1), mode="edge")
    smoothed = np.convolve(padded, kernel, mode="valid")
    mean_v = float(np.mean(smoothed))
    hvn_indices: list[int] = []
    for idx in range(bins_n):
        left_ok = idx == 0 or smoothed[idx] >= smoothed[idx - 1]
        right_ok = idx == bins_n - 1 or smoothed[idx] >= smoothed[idx + 1]
        if left_ok and right_ok and smoothed[idx] >= mean_v * 1.12:
            hvn_indices.append(idx)
    if poc_idx not in hvn_indices:
        hvn_indices.append(poc_idx)

    eff_atr = finite(atr)
    min_sep = max(0.15 * eff_atr, close_now * 0.004) if eff_atr and eff_atr > 0 else close_now * 0.005

    below_hvns = [idx for idx in hvn_indices if float(centers[idx]) <= close_now - min_sep]
    above_hvns = [idx for idx in hvn_indices if float(centers[idx]) >= close_now + min_sep]

    support_hvn: float | None = None
    support_zone_low: float | None = None
    if below_hvns:
        # 下方筹码峰综合考量筹码厚度与邻近度，避免选取过于遥远的陈旧底部峰
        best_sup = max(
            below_hvns,
            key=lambda idx: float(smoothed[idx])
            / (1.0 + abs(close_now - float(centers[idx])) / max(p_max - p_min, 1e-6)),
        )
        support_hvn = round(float(centers[best_sup]), 2)
        support_zone_low = round(float(edges[max(0, best_sup)]), 2)
    elif val_price < close_now:
        support_zone_low = val_price

    resistance_hvn: float | None = None
    resistance_zone_high: float | None = None
    if above_hvns:
        best_res = max(
            above_hvns,
            key=lambda idx: float(smoothed[idx])
            / (1.0 + abs(float(centers[idx]) - close_now) / max(p_max - p_min, 1e-6)),
        )
        resistance_hvn = round(float(centers[best_res]), 2)
        resistance_zone_high = round(float(edges[min(bins_n, best_res + 1)]), 2)
    elif vah_price > close_now:
        resistance_zone_high = vah_price

    # 识别最接近现价且位于主体区间的低量真空谷（LVN）
    lvn_price: float | None = None
    interior_lvn = [
        idx
        for idx in range(1, bins_n - 1)
        if smoothed[idx] <= smoothed[idx - 1]
        and smoothed[idx] <= smoothed[idx + 1]
        and smoothed[idx] <= mean_v * 0.65
    ]
    if interior_lvn:
        nearest_lvn = min(interior_lvn, key=lambda idx: abs(float(centers[idx]) - close_now))
        lvn_price = round(float(centers[nearest_lvn]), 2)

    concentration_pct = round((vah_price - val_price) / max(poc_price, 1e-6) * 100.0, 1)
    near_poc_tol = max(0.6 * eff_atr, close_now * 0.015) if eff_atr and eff_atr > 0 else close_now * 0.015
    if close_now > vah_price:
        pos_label = "站上价值区上沿（上方套牢轻）"
    elif close_now < val_price:
        pos_label = "位于价值区下方（上方套牢偏重）"
    elif abs(close_now - poc_price) <= near_poc_tol:
        pos_label = "贴近主筹码峰（多空成本中枢）"
    else:
        pos_label = "70%筹码价值区内运行"

    max_bucket = float(np.max(bucket_vols))
    bins_payload = [
        {
            "price_low": round(float(edges[idx]), 2),
            "price_high": round(float(edges[idx + 1]), 2),
            "price": round(float(centers[idx]), 2),
            "ratio": round(float(bucket_vols[idx] / max_bucket), 4) if max_bucket > 0 else 0.0,
            "is_poc": idx == poc_idx,
            "in_value_area": va_low_idx <= idx <= va_high_idx,
        }
        for idx in range(bins_n)
    ]

    return {
        "available": True,
        "reason": "",
        "window_days": n,
        "poc": poc_price,
        "vah": vah_price,
        "val": val_price,
        "support_hvn": support_hvn,
        "support_zone_low": support_zone_low,
        "resistance_hvn": resistance_hvn,
        "resistance_zone_high": resistance_zone_high,
        "lvn_price": lvn_price,
        "profit_ratio_pct": profit_ratio_pct,
        "overhead_supply_pct": overhead_supply_pct,
        "concentration_pct": concentration_pct,
        "position_label": pos_label,
        "bins": bins_payload,
    }


def _contiguous_regular_tail(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    reg = frame[frame["session"] == "regular"] if "session" in frame.columns else frame
    if reg.empty:
        return pd.DataFrame()
    valid = (
        reg["close"].notna()
        & np.isfinite(reg["close"])
        & (reg["close"] > 0)
        & reg["high"].notna()
        & np.isfinite(reg["high"])
        & (reg["high"] > 0)
        & reg["low"].notna()
        & np.isfinite(reg["low"])
        & (reg["low"] > 0)
        & (reg["high"] >= reg["low"])
    )
    if "open" in reg.columns:
        valid = valid & reg["open"].notna() & np.isfinite(reg["open"]) & (reg["open"] > 0)
    if valid.empty or not bool(valid.iloc[-1]):
        return pd.DataFrame()
    breaks = (~valid).cumsum()
    # 必须同时保留 valid 掩码，避免将导致断档递增的那一行 NaN 误包含在连续尾部首行
    return reg[valid & (breaks == breaks.iloc[-1])]


def _pick_anchor(
    candidates: list[tuple[str, float] | tuple[str, float, float]],
    low: float,
    high: float,
    target: float,
    fallback: float,
) -> tuple[float, str | None]:
    """在区间 `[low, high]` 内按「距离 target × 亲和系数」选取最具代表性的结构/筹码锚点。"""
    in_range: list[tuple[str, float, float]] = []
    for item in candidates:
        name = item[0]
        val = item[1]
        affinity = item[2] if len(item) >= 3 else 1.0
        if val is not None and low <= val <= high:
            in_range.append((name, val, affinity))
    if in_range:
        chosen_name, chosen_val, _ = min(
            in_range,
            key=lambda item: abs(item[1] - target) * item[2],
        )
        return chosen_val, f"{chosen_name} ${chosen_val:.2f}"
    return fallback, None


def _resolve_key_level(
    candidates: list[tuple[str, float, float]],
    close: float,
    atr: float,
    direction: str,
    fallback_val: float,
    fallback_label: str,
) -> tuple[float, str, bool]:
    """综合筹码分布、波浪结构与均线/箱体候选锚点，提炼主要防守位或突破位并检测多维共振。"""
    valid: list[tuple[str, float, float]] = []
    for label, val, priority in candidates:
        if val is None or not math.isfinite(val) or val <= 0:
            continue
        if direction == "defense" and 0 < val < close:
            valid.append((label, float(val), priority))
        elif direction == "breakout" and val > close:
            valid.append((label, float(val), priority))

    if not valid:
        return round(fallback_val, 2), f"{fallback_label} ${fallback_val:.2f}", False

    # 检测近距多源共振（差值 <= max(0.85*ATR, 1.8%现价)）：多个独立维度重合时可信度显著提高
    cluster_tol = max(0.85 * atr, close * 0.018)
    best_cluster: list[tuple[str, float, float]] = []
    best_score = -1.0
    for _, anchor_val, _ in valid:
        members = [item for item in valid if abs(item[1] - anchor_val) <= cluster_tol]
        # 按优先级加权，并鼓励筹码与结构跨维度共振
        score = sum(item[2] for item in members)
        if score > best_score:
            best_score = score
            best_cluster = members

    # 若共振组有 2 个及以上独立依据，取优先级加权均价作为精确共识位；否则取优先级最高项
    distinct_labels = list(dict.fromkeys(item[0] for item in best_cluster))
    if len(distinct_labels) >= 2:
        w_sum = sum(item[2] for item in best_cluster)
        chosen = sum(item[1] * item[2] for item in best_cluster) / max(w_sum, 1e-6)
        chosen_r = round(chosen, 2)
        if direction == "defense":
            chosen_r = min(round(close - 0.01, 2), max(0.01, chosen_r))
        else:
            chosen_r = max(round(close + 0.01, 2), chosen_r)
        anchor_text = f"{' + '.join(distinct_labels[:2])}共振 ${chosen_r:.2f}"
        return chosen_r, anchor_text, True

    primary = max(best_cluster, key=lambda item: item[2])
    chosen_r = round(primary[1], 2)
    if direction == "defense":
        chosen_r = min(round(close - 0.01, 2), max(0.01, chosen_r))
    else:
        chosen_r = max(round(close + 0.01, 2), chosen_r)
    return chosen_r, f"{primary[0]} ${chosen_r:.2f}", False


def compute_forecast(
    frame: pd.DataFrame | None,
    summary: dict,
    research: dict,
    long_plan: dict,
    instrument: dict | None = None,
    fund_metrics: dict | None = None,
    factors: dict | None = None,
    wave_trend: dict | None = None,
    macro: dict | None = None,
) -> dict:
    """Compute causal support/resistance price levels, 5-tier rating, and risk budget."""
    tail = _contiguous_regular_tail(frame)
    if (
        len(tail) < 60
        or not summary.get("valid")
        or not summary.get("confirmed_price_available")
    ):
        return _unavailable_payload()

    close = finite(long_plan.get("close"))
    if close is None:
        close = finite(summary.get("close"))
    indicators = summary.get("indicators") or {}
    atr = finite(indicators.get("atr"))
    if close is None or close < 0.05 or atr is None or atr <= 0:
        return _unavailable_payload()

    tail20 = tail.tail(20)
    tail60 = tail.tail(60)
    low_20 = finite(tail20["low"].min())
    high_20 = finite(tail20["high"].max())
    low_60 = finite(tail60["low"].min())
    high_60 = finite(tail60["high"].max())
    if None in (low_20, high_20, low_60, high_60):
        return _unavailable_payload()

    ma20 = finite(indicators.get("ma20"))
    ma50 = finite(indicators.get("ma50"))
    ma200 = finite(indicators.get("ma200"))
    bb_lower = finite(indicators.get("bb_lower"))
    bb_upper = finite(indicators.get("bb_upper"))
    rsi = finite(indicators.get("rsi"))

    wt_trend = (wave_trend or {}).get("trend") or {}
    wt_dir = str(wt_trend.get("direction") or "")
    wt_breakout = finite(wt_trend.get("breakout_level"))
    wt_inval = finite(wt_trend.get("invalidation_level"))

    # 计算 126 日严格因果筹码分布（Volume Profile），提供真实成交量堆积的支撑与压力锚点
    vp = compute_volume_profile(tail, atr=atr, window=126, num_bins=28)
    vp_poc = finite(vp.get("poc")) if vp.get("available") else None
    vp_val = finite(vp.get("val")) if vp.get("available") else None
    vp_vah = finite(vp.get("vah")) if vp.get("available") else None
    vp_sup_hvn = finite(vp.get("support_hvn")) if vp.get("available") else None
    vp_sup_low = finite(vp.get("support_zone_low")) if vp.get("available") else None
    vp_res_hvn = finite(vp.get("resistance_hvn")) if vp.get("available") else None
    vp_res_high = finite(vp.get("resistance_zone_high")) if vp.get("available") else None

    pivot = (high_20 + low_20 + close) / 3.0
    s1 = 2.0 * pivot - high_20
    r1 = 2.0 * pivot - low_20

    # 1) Buy high (去重后的支撑锚点：优先筹码密集承接区 POC/VAL/下方筹码峰 + 波浪前低 + 均线)
    bh_candidates = [
        (name, val, affinity)
        for name, val, affinity in [
            ("主筹码峰 POC", vp_poc if vp_poc is not None and vp_poc <= close else None, 0.72),
            ("下方筹码峰", vp_sup_hvn, 0.74),
            ("筹码价值区下沿 VAL", vp_val if vp_val is not None and vp_val <= close else None, 0.76),
            ("波浪前低", wt_inval if wt_dir != "downtrend" else None, 0.80),
            ("MA20 均线", ma20, 0.92),
            ("MA50 均线", ma50, 0.88),
            ("MA200 年线", ma200, 0.88),
            ("枢轴支撑 S1", s1, 1.0),
            ("20日低点", low_20, 0.95),
        ]
        if val is not None
    ]
    bh_fallback = max(
        0.03,
        close - (0.45 * atr if rsi is not None and rsi <= 35 else 0.75 * atr),
    )
    bh_raw, bh_anchor = _pick_anchor(
        bh_candidates, max(0.03, close - 1.6 * atr), close, close - 0.55 * atr, bh_fallback
    )
    bh_raw = min(close, max(0.03, bh_raw))

    # 2) Buy low (深层结构与筹码下沿支撑)
    bl_candidates = [
        (name, val, affinity)
        for name, val, affinity in [
            ("筹码价值区下沿 VAL", vp_val if vp_val is not None and vp_val < bh_raw else None, 0.72),
            ("下方筹码支撑下沿", vp_sup_low if vp_sup_low is not None and vp_sup_low < bh_raw else None, 0.74),
            ("下方筹码峰", vp_sup_hvn if vp_sup_hvn is not None and vp_sup_hvn < bh_raw else None, 0.76),
            ("波浪前低", wt_inval if wt_dir != "downtrend" else None, 0.78),
            ("MA50 支撑", ma50, 0.88),
            ("MA200 支撑", ma200, 0.86),
            ("布林下轨", bb_lower, 0.96),
            ("20日低点", low_20, 0.94),
            ("60日低点", low_60, 0.95),
            ("枢轴支撑 S1", s1, 1.0),
        ]
        if val is not None
    ]
    bl_low_bound = max(0.02, min(bh_raw - 0.02, close - 3.2 * atr))
    bl_high_bound = max(bl_low_bound, bh_raw - 0.45 * atr)
    bl_fallback = max(0.02, min(bl_high_bound, bh_raw - 1.1 * atr))
    bl_raw, bl_anchor = _pick_anchor(
        bl_candidates, bl_low_bound, bl_high_bound, bh_raw - 1.1 * atr, bl_fallback
    )

    # 3) Stop loss (防跌破买区下沿与筹码支撑下沿的 ATR 防守位)
    stop_struct_refs = [x for x in (low_20, vp_sup_low, vp_val) if x is not None and x < close]
    stop_ref_low = min(stop_struct_refs) if stop_struct_refs else low_20
    stop_candidate = min(bl_raw - 0.75 * atr, stop_ref_low - 0.35 * atr)
    stop_floor = max(0.01, min(bl_raw - 0.02, bl_raw - 2.2 * atr))
    stop_ceil = max(stop_floor, min(bl_raw - 0.01, bl_raw - 0.5 * atr))
    stop_raw = min(stop_ceil, max(stop_floor, stop_candidate))

    # 4) First sell target (筹码压力上沿 / 波浪前高 / 波动通道压力)
    sl_candidates = [
        (name, val, affinity)
        for name, val, affinity in [
            ("上方筹码峰", vp_res_hvn, 0.74),
            ("筹码价值区上沿 VAH", vp_vah if vp_vah is not None and vp_vah > close else None, 0.74),
            ("波浪前高", wt_breakout, 0.76),
            ("20日高点压力", high_20, 0.88),
            ("布林上轨", bb_upper, 0.94),
            ("枢轴阻力 R1", r1, 1.0),
            ("MA20 压力", ma20, 0.95),
            ("MA50 压力", ma50, 0.92),
            ("MA200 压力", ma200, 0.90),
        ]
        if val is not None
    ]
    sl_raw, sl_anchor = _pick_anchor(
        sl_candidates, close + 0.85 * atr, close + 3.2 * atr, close + 1.8 * atr, close + 1.8 * atr
    )

    # 5) Second sell target (波段高点 / 上方筹码密集区上沿 / 中长期压力)
    sh_candidates = [
        (name, val, affinity)
        for name, val, affinity in [
            ("筹码压力上沿", vp_res_high if vp_res_high is not None and vp_res_high > sl_raw else None, 0.74),
            ("筹码价值区上沿 VAH", vp_vah if vp_vah is not None and vp_vah > sl_raw else None, 0.76),
            ("60日高点阻力", high_60, 0.85),
            ("空头反转前高", wt_inval if wt_dir == "downtrend" else None, 0.80),
            ("布林上轨", bb_upper, 0.96),
            ("枢轴阻力 R1", r1, 1.0),
            ("MA200 压力", ma200, 0.92),
        ]
        if val is not None
    ]
    sh_raw, sh_anchor = _pick_anchor(
        sh_candidates, sl_raw + 0.8 * atr, close + 5.8 * atr, sl_raw + 1.6 * atr, sl_raw + 1.6 * atr
    )

    # Strict monotonic precision enforcement: 0 < stop_loss < buy_low < buy_high <= close < sell_low < sell_high
    close_floor = math.floor(close * 100.0 + 1e-9) / 100.0
    buy_high = min(close_floor, max(0.03, round(bh_raw, 2)))
    buy_low = min(round(buy_high - 0.01, 2), max(0.02, round(bl_raw, 2)))
    if buy_low >= buy_high:
        buy_low = round(max(0.02, buy_high - 0.01), 2)
    stop_loss = min(round(buy_low - 0.01, 2), max(0.01, round(stop_raw, 2)))
    if stop_loss >= buy_low:
        stop_loss = round(max(0.01, buy_low - 0.01), 2)

    sell_low = max(round(close_floor + 0.01, 2), round(sl_raw, 2))
    if sell_low <= close:
        sell_low = round(sell_low + 0.01, 2)
    sell_high = max(round(sell_low + 0.01, 2), round(sh_raw, 2))
    ideal_buy = round((buy_low + buy_high) / 2.0, 2)

    # 6) 提炼 K 线主图两大核心实战点位：主要防守位（defense_level）与主要突破位（breakout_level）
    # 提前计算 60 日峰值移动保护位，参与多维防守锚点共振评估
    peak_60d = round(high_60, 2)
    trailing_stop = round(max(0.01, peak_60d - 2.5 * atr), 2)

    def _in_band(val: float | None, lo_mult: float, hi_mult: float, above: bool) -> float | None:
        if val is None or not math.isfinite(val) or val <= 0:
            return None
        dist = (val - close) if above else (close - val)
        if lo_mult * atr <= dist <= hi_mult * atr:
            return val
        return None

    defense_candidates: list[tuple[str, float, float]] = []
    for label, cand_val, prio in [
        ("筹码价值区下沿 VAL", _in_band(vp_val, 0.45, 4.5, False), 1.35),
        ("下方筹码支撑下沿", _in_band(vp_sup_low, 0.45, 4.5, False), 1.25),
        ("波浪前低", _in_band(wt_inval if wt_dir != "downtrend" else None, 0.45, 4.8, False), 1.35),
        ("60日移动保护", _in_band(trailing_stop, 0.45, 4.2, False), 1.05),
        ("20日箱体下沿", _in_band(low_20, 0.45, 4.2, False), 0.95),
        ("MA200 年线", _in_band(ma200, 0.5, 4.0, False), 0.90),
    ]:
        if cand_val is not None:
            defense_candidates.append((label, cand_val, prio))
    defense_level, defense_anchor, defense_confluence = _resolve_key_level(
        defense_candidates,
        close=close,
        atr=atr,
        direction="defense",
        fallback_val=stop_loss,
        fallback_label="ATR 防守止损",
    )

    breakout_candidates: list[tuple[str, float, float]] = []
    for label, cand_val, prio in [
        ("波浪前高", _in_band(wt_breakout, 0.35, 5.2, True), 1.35),
        ("空头反转前高", _in_band(wt_inval if wt_dir == "downtrend" else None, 0.35, 5.5, True), 1.35),
        ("筹码价值区上沿 VAH", _in_band(vp_vah, 0.35, 5.0, True), 1.35),
        ("上方筹码压力上沿", _in_band(vp_res_high, 0.35, 5.2, True), 1.25),
        ("20日箱体上沿", _in_band(high_20, 0.35, 4.8, True), 1.05),
        ("60日高点阻力", _in_band(high_60, 0.5, 5.5, True), 1.0),
    ]:
        if cand_val is not None:
            breakout_candidates.append((label, cand_val, prio))
    breakout_level, breakout_anchor, breakout_confluence = _resolve_key_level(
        breakout_candidates,
        close=close,
        atr=atr,
        direction="breakout",
        fallback_val=sell_low,
        fallback_label="第一阻力参考",
    )

    buy_discount_pct = round((buy_high / close - 1.0) * 100.0, 2)
    upside_pct = round((sell_low / close - 1.0) * 100.0, 2)
    target_upside_pct = round((sell_high / close - 1.0) * 100.0, 2)
    downside_pct = round((stop_loss / close - 1.0) * 100.0, 2)
    risk_reward_ratio = round((sell_low - close) / max(close - stop_loss, 1e-6), 2)
    entry_risk_reward_ratio = round((sell_low - buy_high) / max(buy_high - stop_loss, 1e-6), 2)

    if buy_discount_pct >= -1.5:
        position_label = "接近买点区"
    elif upside_pct <= 4.0:
        position_label = "接近卖点压力"
    else:
        position_label = "区间中段"

    buy_anchors = [
        bh_anchor or f"ATR14 回调 ${buy_high:.2f}",
        bl_anchor or f"ATR14 支撑 ${buy_low:.2f}",
    ]
    if vp.get("available") and vp_val is not None and vp_val <= close:
        val_tag = f"筹码价值区下沿 VAL ${vp_val:.2f}"
        if not any("VAL" in a for a in buy_anchors):
            buy_anchors.append(val_tag)
    buy_anchors = list(dict.fromkeys(buy_anchors))[:3]

    sell_anchors = [
        sl_anchor or f"ATR14 一卖 ${sell_low:.2f}",
        sh_anchor or f"ATR14 二卖 ${sell_high:.2f}",
    ]
    if vp.get("available") and vp_vah is not None and vp_vah >= close:
        vah_tag = f"筹码价值区上沿 VAH ${vp_vah:.2f}"
        if not any("VAH" in a for a in sell_anchors):
            sell_anchors.append(vah_tag)
    sell_anchors = list(dict.fromkeys(sell_anchors))[:3]

    if vp.get("available") and vp_sup_low is not None and abs(stop_ref_low - vp_sup_low) <= 0.05:
        stop_anchor = f"筹码支撑下沿(${vp_sup_low:.2f})下方 ATR14 防守"
    elif vp.get("available") and vp_val is not None and abs(stop_ref_low - vp_val) <= 0.05:
        stop_anchor = f"筹码价值区下沿(${vp_val:.2f})下方 ATR14 防守"
    else:
        stop_anchor = f"20日低点(${low_20:.2f})下方 ATR14 防守"

    levels = {
        "available": True,
        "reason": "",
        "buy_low": buy_low,
        "buy_high": buy_high,
        "ideal_buy": ideal_buy,
        "sell_low": sell_low,
        "sell_high": sell_high,
        "stop_loss": stop_loss,
        "defense_level": defense_level,
        "defense_anchor": defense_anchor,
        "defense_confluence": defense_confluence,
        "breakout_level": breakout_level,
        "breakout_anchor": breakout_anchor,
        "breakout_confluence": breakout_confluence,
        "buy_discount_pct": buy_discount_pct,
        "upside_pct": upside_pct,
        "target_upside_pct": target_upside_pct,
        "downside_pct": downside_pct,
        "risk_reward_ratio": risk_reward_ratio,
        "entry_risk_reward_ratio": entry_risk_reward_ratio,
        "position_label": position_label,
        "buy_anchors": buy_anchors,
        "sell_anchors": sell_anchors,
        "stop_anchor": stop_anchor,
    }

    # 5-tier Rating calculation (个股 vs ETF/指数基金正交四维评估，消除二次扣分)
    base_tech_score = float(summary["score"])
    state_label = {"strong": "结构偏强", "weak": "结构偏弱", "neutral": "结构中性"}.get(
        summary.get("state", "neutral"), "待确认"
    )
    inst = instrument or {}
    is_fund = bool(inst.get("is_fund"))
    is_leveraged = bool(inst.get("is_leveraged"))
    is_inverse = bool(inst.get("is_inverse"))
    fm = fund_metrics or {}

    fac = factors or {}
    res_mom = finite(fac.get("residual_mom_z"))
    id_label = fac.get("id_label")
    h52_ratio = finite(fac.get("high_52w_ratio"))

    res_adj = (
        float(np.clip(res_mom * 3.5, -6.0, 6.0))
        if (res_mom is not None and not is_inverse)
        else 0.0
    )
    id_adj = (
        3.5
        if (id_label == "连续慢牛" and not is_inverse)
        else (-3.5 if (id_label == "脉冲跳涨" and not is_inverse) else 0.0)
    )
    h52_adj = 2.5 if (not is_fund and h52_ratio is not None and h52_ratio >= 0.88) else 0.0
    tech_score = float(np.clip(base_tech_score + res_adj + id_adj + h52_adj, 5.0, 98.0))
    tech_parts = [f"日线 {base_tech_score:.1f}（{state_label}）"]
    if res_mom is not None:
        tech_parts.append(f"残差动量 {res_mom:+.2f}")
    if id_label:
        tech_parts.append(str(id_label))
    tech_detail = " · ".join(tech_parts)

    val = research.get("valuation") or {}
    val_fresh = bool(val.get("fresh"))
    curve = research.get("curve") or {}
    curve_fresh = bool(curve.get("fresh"))
    ten_change_bp = finite(curve.get("ten_change_bp"))
    pe = finite(val.get("pe_ttm"))
    div = finite(val.get("dividend_yield_pct")) or 0.0
    gap = finite(research.get("yield_gap_pp"))
    real_gap = finite(research.get("real_yield_gap_pp"))

    rr_score = float(
        np.clip(
            30.0 + risk_reward_ratio * 25.0 + (8.0 if buy_discount_pct >= -2.0 else 0.0),
            15.0,
            95.0,
        )
    )
    rr_detail = f"现价盈亏比 {risk_reward_ratio:.2f}:1（距参考买点 {buy_discount_pct:+.1f}%）"

    risks = list(summary.get("risks") or [])
    stale_risk = any("过期" in r for r in risks)

    # 尾部与流动性正交风控分：不再重复扣减日线已计入的 RSI/MA20 偏离，聚焦 MAX5 彩票/下行Beta/跳空波动/摩擦成本
    rc_score = 88.0
    rc_flags: list[str] = []
    if fac.get("lottery_overheated"):
        rc_score -= 18.0
        rc_flags.append("MAX5 急涨过热")
    downside_beta = finite(fac.get("downside_beta"))
    if downside_beta is not None:
        if downside_beta >= 1.5:
            rc_score -= 12.0
            rc_flags.append(f"下行Beta {downside_beta:.2f}")
        elif downside_beta >= 1.25:
            rc_score -= 6.0
    yz_hv60 = finite(fac.get("yang_zhang_hv60_pct"))
    hv60 = yz_hv60 if yz_hv60 is not None else finite(fm.get("hv60_pct"))
    if is_leveraged and hv60 is not None:
        if hv60 >= 75.0:
            rc_score -= 18.0
        elif hv60 >= 55.0:
            rc_score -= 10.0
        elif hv60 >= 40.0:
            rc_score -= 5.0
    elif hv60 is not None:
        if hv60 >= 60.0:
            rc_score -= 12.0
            rc_flags.append(f"年化波动 {hv60:.1f}%")
        elif hv60 >= 42.0:
            rc_score -= 6.0
    if fac.get("illiquid_flag"):
        rc_score -= 12.0
        rc_flags.append("流动性偏弱")
    if fac.get("high_turnover_flag"):
        rc_score -= 8.0
        rc_flags.append("高换手拥挤")
    if stale_risk:
        rc_score -= 10.0
        rc_flags.append("行情待同步")

    rc_score = max(10.0, rc_score)

    if is_fund:
        dd_high = finite(fm.get("drawdown_from_high_pct"))
        pos_52w = finite(fm.get("range_position_pct"))
        ma200_gap = finite(fm.get("ma200_gap_pct"))
        # 基金/指数不使用失真的单股 PE/PB，改用近1年回撤分位、年线偏离与美债长端变动评估
        if dd_high is not None and pos_52w is not None:
            if pos_52w >= 90.0:
                base_pos = 50.0  # 贴近52周高点，防高位追涨
            elif pos_52w >= 65.0:
                base_pos = 64.0  # 偏强区中上沿
            elif pos_52w >= 30.0:
                base_pos = 72.0  # 合理回调/中段性价比区
            elif dd_high >= -22.0:
                base_pos = 62.0  # 较深回撤但仍可控
            else:
                base_pos = 44.0  # 深度回撤弱势区，待企稳确认

            macro_adj = 0.0
            macro_note = ""
            if curve_fresh and ten_change_bp is not None and not is_inverse:
                if ten_change_bp <= -10.0:
                    macro_adj = 5.0
                    macro_note = f" · 10Y近21日 {ten_change_bp:+.0f}bp"
                elif ten_change_bp >= 15.0:
                    macro_adj = -5.0
                    macro_note = f" · 10Y近21日 {ten_change_bp:+.0f}bp"
            ma_adj = 3.0 if (ma200_gap is not None and 0 <= ma200_gap <= 15.0) else (
                -4.0 if (ma200_gap is not None and ma200_gap < -12.0) else 0.0
            )
            fund_pos_score: float | None = float(np.clip(base_pos + macro_adj + ma_adj, 18.0, 90.0))
            fund_pos_detail = (
                f"距52周高点 {dd_high:+.1f}% · 年内分位 {pos_52w:.0f}%{macro_note}"
            )
        else:
            fund_pos_score = None
            fund_pos_detail = "历史样本不足60日，权重按其余维度归一化"

        if is_leveraged:
            vol_text = f"Yang-Zhang波动 {hv60:.1f}%（存在杠杆损耗）" if hv60 is not None else "日度再平衡杠杆损耗"
            rc_detail = f"{vol_text} · {' · '.join(rc_flags)}" if rc_flags else vol_text
            raw_factors = [
                {"key": "technical", "label": "技术结构", "base_weight": 0.45, "score": tech_score, "detail": tech_detail},
                {"key": "fund_position", "label": "波动与回撤", "base_weight": 0.20, "score": fund_pos_score, "detail": fund_pos_detail},
                {"key": "risk_reward", "label": "点位赔率", "base_weight": 0.20, "score": rr_score, "detail": rr_detail},
                {"key": "risk_control", "label": "杠杆风控", "base_weight": 0.15, "score": rc_score, "detail": rc_detail},
            ]
        else:
            vol_prefix = f"年化波动 {hv60:.1f}%" if hv60 is not None else "波动评估平稳"
            rc_detail = f"{vol_prefix} · {' · '.join(rc_flags)}" if rc_flags else f"{vol_prefix} · 尾部风险可控"
            raw_factors = [
                {"key": "technical", "label": "技术结构", "base_weight": 0.40, "score": tech_score, "detail": tech_detail},
                {"key": "fund_position", "label": "回撤与宏观", "base_weight": 0.25, "score": fund_pos_score, "detail": fund_pos_detail},
                {"key": "risk_reward", "label": "点位赔率", "base_weight": 0.25, "score": rr_score, "detail": rr_detail},
                {"key": "risk_control", "label": "风险控制", "base_weight": 0.10, "score": rc_score, "detail": rc_detail},
            ]
    else:
        if val_fresh:
            if pe is not None and pe <= 0:
                val_score: float | None = 18.0
                val_detail = f"滚动 PE {pe:.1f}x（盈利为负，估值承压）"
            elif gap is not None and pe is not None:
                eff_gap = 0.5 * gap + 0.5 * (real_gap - 1.5) if real_gap is not None else gap
                val_score = float(np.clip(58.0 + eff_gap * 10.0 + (4.0 if div >= 2.0 else 0.0), 15.0, 95.0))
                real_note = f" / 实际 {real_gap:+.2f}pp" if real_gap is not None else ""
                val_detail = f"PE {pe:.1f}x，股债利差 {gap:+.2f}pp{real_note}"
            elif pe is not None and pe > 0:
                val_score = float(np.clip(90.0 - pe * 1.15 + (4.0 if div >= 2.0 else 0.0), 20.0, 82.0))
                val_detail = f"PE {pe:.1f}x（缺有效美债利率对照，按市盈率水平估算）"
            else:
                val_score = None
                val_detail = "暂无有效市盈率，权重按其余维度归一化"
        else:
            val_score = None
            val_detail = "估值数据未更新或已过期，权重按其余维度归一化"

        rc_detail = (
            " · ".join(rc_flags)
            if rc_flags
            else (
                f"波动 {hv60:.1f}% · 尾部风险可控"
                if hv60 is not None
                else "尾部与流动性风险可控"
            )
        )
        raw_factors = [
            {"key": "technical", "label": "技术结构", "base_weight": 0.40, "score": tech_score, "detail": tech_detail},
            {"key": "valuation", "label": "估值利率", "base_weight": 0.30, "score": val_score, "detail": val_detail},
            {"key": "risk_reward", "label": "点位赔率", "base_weight": 0.20, "score": rr_score, "detail": rr_detail},
            {"key": "risk_control", "label": "风险控制", "base_weight": 0.10, "score": rc_score, "detail": rc_detail},
        ]

    active_weight = sum(f["base_weight"] for f in raw_factors if f["score"] is not None)
    rating_factors = []
    raw_score = 0.0
    for item in raw_factors:
        eff_weight = item["base_weight"] / active_weight if item["score"] is not None else 0.0
        if item["score"] is not None:
            raw_score += item["score"] * eff_weight
        rating_factors.append(
            {
                "key": item["key"],
                "label": item["label"],
                "weight": round(eff_weight, 4),
                "score": round(item["score"], 1) if item["score"] is not None else None,
                "detail": item["detail"],
            }
        )
    raw_score = round(raw_score, 1)

    if raw_score >= 78.0:
        code = "strong_buy"
    elif raw_score >= 64.0:
        code = "buy"
    elif raw_score >= 46.0:
        code = "hold"
    elif raw_score >= 32.0:
        code = "reduce"
    else:
        code = "sell"

    guardrails: list[str] = []

    def cap_tier(max_code: str):
        nonlocal code
        if TIER_ORDER.index(code) > TIER_ORDER.index(max_code):
            code = max_code

    plan_stop = finite(long_plan.get("stop"))
    if plan_stop is not None and close <= plan_stop:
        cap_tier("reduce")
        guardrails.append(f"已跌破个人计划失效价 ${plan_stop:.2f}，风控护栏将评级上限设为谨慎减持")

    if not is_fund and val_fresh and pe is not None and pe <= 0:
        cap_tier("hold")
        guardrails.append(f"滚动市盈率为负（PE {pe:.1f}x），风控护栏暂不给出买入评级")

    trend_dim = finite((summary.get("dimensions") or {}).get("trend"))
    if summary.get("state") == "weak" and trend_dim is not None and trend_dim < 25:
        cap_tier("hold")
        guardrails.append("日线处于空头弱势结构，风控护栏暂停买入提示")

    max5_val = finite(fac.get("max5_21d_pct"))
    if (
        not is_fund
        and fac.get("lottery_overheated")
        and ma20 is not None
        and ma20 > 0
        and close > ma20 + 2.0 * atr
    ):
        cap_tier("hold")
        guardrails.append(
            f"近月单日急涨过热（MAX5 {max5_val:.1f}%），谨防彩票型脉冲回落，暂不追高"
            if max5_val is not None
            else "近月单日急涨过热（MAX5 偏高），谨防彩票型脉冲回落，暂不追高"
        )

    if is_inverse:
        cap_tier("hold")
        guardrails.append("属于反向做空杠杆工具，存在每日再平衡损耗，仅作短线对冲参考，暂不出具买入评级")
    elif is_leveraged:
        cap_tier("buy")
        guardrails.append("属于高倍杠杆交易型基金，存在每日复利波动损耗，仅适合波段跟踪并须严守止损")

    if is_fund:
        fund_ready = bool(fm.get("available") and fm.get("range_position_pct") is not None)
        if fund_ready and curve_fresh and not stale_risk and len(risks) < 3 and not is_leveraged:
            confidence = "高"
        elif (fund_ready or curve_fresh) and not stale_risk and len(risks) < 3:
            confidence = "中"
        else:
            confidence = "低"
    else:
        if val_fresh and curve_fresh and not stale_risk and len(risks) < 3:
            confidence = "高"
        elif (val_fresh or curve_fresh) and not stale_risk and len(risks) < 3:
            confidence = "中"
        else:
            confidence = "低"

    # 波动率参考仓位预算与 60 日客观峰值移动保护位（Moreira & Muir 2017; Han, Zhou & Zhu 2016）
    eff_yz_hv = (
        finite(fac.get("yang_zhang_hv60_pct"))
        or finite(fac.get("yang_zhang_hv20_pct"))
        or finite(fm.get("hv60_pct"))
        or round((atr / close) * math.sqrt(252.0) * 100.0, 1)
    )
    vol_scale = round(float(np.clip(20.0 / max(eff_yz_hv, 8.0), 0.25, 1.25)), 2)
    raw_red = ((macro or {}).get("risk_gauge") or {}).get("red_count")
    macro_red_count = int(raw_red) if isinstance(raw_red, (int, float)) and math.isfinite(raw_red) else None
    if macro_red_count is not None and macro_red_count >= 4:
        macro_multiplier = 0.70
        macro_label = f"宏观逆风 红灯{macro_red_count}/6"
    elif macro_red_count == 3:
        macro_multiplier = 0.85
        macro_label = "宏观审慎 红灯3/6"
    elif macro_red_count is not None:
        macro_multiplier = 1.0
        macro_label = f"宏观平稳 红灯{macro_red_count}/6"
    else:
        macro_multiplier = 1.0
        macro_label = "宏观基准"
    suggested_exposure_ratio = round(float(np.clip(vol_scale * macro_multiplier, 0.20, 1.25)), 2)

    trailing_drawdown_pct = round((close / peak_60d - 1.0) * 100.0, 2) if peak_60d > 0 else None
    trailing_breached = bool(close <= trailing_stop)
    risk_budget = {
        "available": True,
        "yz_hv_pct": round(float(eff_yz_hv), 1),
        "vol_scale": vol_scale,
        "macro_red_count": macro_red_count,
        "macro_multiplier": macro_multiplier,
        "macro_label": macro_label,
        "suggested_exposure_ratio": suggested_exposure_ratio,
        "trailing_stop": trailing_stop,
        "peak_60d": peak_60d,
        "trailing_drawdown_pct": trailing_drawdown_pct,
        "trailing_breached": trailing_breached,
        "note": (
            f"目标20%波动：Yang-Zhang({eff_yz_hv:.1f}%) 系数 {vol_scale:.2f}x × "
            f"{macro_label} ({macro_multiplier:.2f}) = {suggested_exposure_ratio:.2f}x"
        ),
    }

    label, tone, stars = TIER_SPECS[code]
    guard_note = f"（已触发风控护栏：{guardrails[0]}）" if guardrails else ""
    rating_summary = (
        f"综合评级「{label}」（{raw_score:.1f}分，置信度{confidence}）："
        f"防守 ${defense_level:.2f} / 突破 ${breakout_level:.2f}，"
        f"参考买点 ${buy_low:.2f}–${buy_high:.2f}，现价盈亏比 {risk_reward_ratio:.2f}:1{guard_note}。"
    )

    return {
        "levels": levels,
        "volume_profile": vp,
        "rating": {
            "available": True,
            "code": code,
            "label": label,
            "tone": tone,
            "score": raw_score,
            "stars": stars,
            "confidence": confidence,
            "summary": rating_summary,
            "factors": rating_factors,
            "guardrails": guardrails,
            "disclaimer": ETF_DISCLAIMER if is_fund else DISCLAIMER,
        },
        "risk_budget": risk_budget,
    }
