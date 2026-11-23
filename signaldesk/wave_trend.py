"""Causal Elliott Wave & Trend Channel analysis for US daily candlesticks."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .calendar import NY
from .forecast import _contiguous_regular_tail
from .indicators import finite

WAVE_DISCLAIMER = "基于已确认日线与因果拐点算法测算波浪与趋势通道，仅作结构复核参考，不构成投资建议。"


def _unavailable_wave_trend(reason: str = "有效连续常规日线不足 60 根，暂不识别波浪与趋势结构") -> dict:
    return {
        "available": False,
        "reason": reason,
        "summary": "有效日线样本尚不足，暂不生成波浪与趋势结构标注。",
        "action_guide": "等待至少 60 根连续已确认常规日线完成后自动计算趋势通道与波段结构。",
        "trend": {
            "direction": "unavailable",
            "label": "趋势待确认",
            "tone": "muted",
            "structure": "摆动样本不足",
            "structure_code": "",
            "ma_alignment": "均线待确认",
            "slope_pct_per_20d": None,
            "channel_position_pct": None,
            "channel_position_label": "数据待补",
            "breakout_level": None,
            "invalidation_level": None,
            "channel": {"available": False},
        },
        "wave": {
            "pattern": "unavailable",
            "pattern_label": "波浪待确认",
            "current_wave": "",
            "phase_label": "样本不足，暂不标浪",
            "tone": "muted",
            "confidence": "低",
            "rules_passed": [],
            "fib_targets": [],
            "pivots": [],
        },
        "disclaimer": WAVE_DISCLAIMER,
    }


def _ny_date_str(ts) -> str:
    if isinstance(ts, pd.Timestamp):
        dt = ts.to_pydatetime()
    else:
        dt = ts
    return dt.astimezone(NY).date().isoformat()


def _causal_swings(tail: pd.DataFrame) -> list[dict]:
    """Strictly causal ATR-adaptive swing detection (no future bar lookahead)."""
    if tail is None or tail.empty:
        return []
    valid_mask = (
        tail["high"].notna()
        & tail["low"].notna()
        & tail["close"].notna()
        & np.isfinite(tail["high"])
        & np.isfinite(tail["low"])
        & np.isfinite(tail["close"])
        & (tail["high"] > 0)
        & (tail["low"] > 0)
        & (tail["close"] > 0)
    )
    clean = tail[valid_mask]
    highs = clean["high"].to_numpy(dtype=float)
    lows = clean["low"].to_numpy(dtype=float)
    closes = clean["close"].to_numpy(dtype=float)
    dates = [_ny_date_str(ts) for ts in clean["timestamp"]]
    n = len(clean)
    if n < 20:
        return []

    if "atr" in clean.columns:
        atrs = clean["atr"].to_numpy(dtype=float)
    else:
        atrs = np.full(n, np.nan, dtype=float)

    # Causal fallback range for early bars where ATR14 is still warming up.
    bar_ranges = np.maximum(highs - lows, closes * 0.01)
    running_range = pd.Series(bar_ranges).rolling(14, min_periods=1).mean().to_numpy(dtype=float)

    def threshold_at(idx: int) -> float:
        a = atrs[idx]
        if not np.isfinite(a) or a <= 0:
            a = running_range[idx]
        return max(2.2 * float(a), 0.045 * float(closes[idx]))

    swings: list[dict] = []
    direction = 0  # 0 undecided, 1 tracking upward leg, -1 tracking downward leg
    hi_idx = 0
    hi_val = highs[0]
    lo_idx = 0
    lo_val = lows[0]

    for i in range(1, n):
        th = threshold_at(i)
        h = highs[i]
        lo = lows[i]

        if direction == 0:
            if h >= hi_val:
                hi_idx, hi_val = i, h
            if lo <= lo_val:
                lo_idx, lo_val = i, lo
            if h >= lo_val + th and lo_idx < i:
                swings.append(
                    {
                        "idx": lo_idx,
                        "date": dates[lo_idx],
                        "price": round(float(lo_val), 2),
                        "kind": "L",
                        "confirmed": True,
                    }
                )
                direction = 1
                hi_idx, hi_val = i, h
            elif lo <= hi_val - th and hi_idx < i:
                swings.append(
                    {
                        "idx": hi_idx,
                        "date": dates[hi_idx],
                        "price": round(float(hi_val), 2),
                        "kind": "H",
                        "confirmed": True,
                    }
                )
                direction = -1
                lo_idx, lo_val = i, lo
        elif direction == 1:
            if h >= hi_val:
                hi_idx, hi_val = i, h
            elif lo <= hi_val - th:
                swings.append(
                    {
                        "idx": hi_idx,
                        "date": dates[hi_idx],
                        "price": round(float(hi_val), 2),
                        "kind": "H",
                        "confirmed": True,
                    }
                )
                direction = -1
                lo_idx, lo_val = i, lo
        else:
            if lo <= lo_val:
                lo_idx, lo_val = i, lo
            elif h >= lo_val + th:
                swings.append(
                    {
                        "idx": lo_idx,
                        "date": dates[lo_idx],
                        "price": round(float(lo_val), 2),
                        "kind": "L",
                        "confirmed": True,
                    }
                )
                direction = 1
                hi_idx, hi_val = i, h

    # Append the live unconfirmed endpoint cleanly separated via confirmed=False.
    last_idx = swings[-1]["idx"] if swings else -1
    if direction == 1 and hi_idx > last_idx:
        swings.append(
            {
                "idx": hi_idx,
                "date": dates[hi_idx],
                "price": round(float(hi_val), 2),
                "kind": "H",
                "confirmed": False,
            }
        )
    elif direction == -1 and lo_idx > last_idx:
        swings.append(
            {
                "idx": lo_idx,
                "date": dates[lo_idx],
                "price": round(float(lo_val), 2),
                "kind": "L",
                "confirmed": False,
            }
        )

    # Annotate Dow Theory structure (HH / HL / LH / LL).
    prev_h: float | None = None
    prev_l: float | None = None
    for item in swings:
        if item["kind"] == "H":
            if prev_h is None:
                item["structure"] = "H"
            else:
                item["structure"] = "HH" if item["price"] > prev_h else "LH"
            if item["confirmed"]:
                prev_h = item["price"]
        else:
            if prev_l is None:
                item["structure"] = "L"
            else:
                item["structure"] = "HL" if item["price"] > prev_l else "LL"
            if item["confirmed"]:
                prev_l = item["price"]
        item["wave_label"] = ""
    return swings


def _compute_trend_channel(tail: pd.DataFrame, atr: float) -> dict:
    """Linear regression parallel trend channel over the recent confirmed window."""
    win = min(len(tail), 90)
    if win < 30:
        return {"available": False}
    seg = tail.tail(win)
    closes = seg["close"].to_numpy(dtype=float)
    x = np.arange(win, dtype=float)
    slope, intercept = np.polyfit(x, closes, 1)
    mid_line = intercept + slope * x
    resid = closes - mid_line
    std_resid = float(np.std(resid, ddof=0))
    p88 = float(np.percentile(np.abs(resid), 88))
    band = max(1.75 * std_resid, p88, atr * 1.25, float(closes[-1]) * 0.02)

    start_mid = float(mid_line[0])
    end_mid = float(mid_line[-1])
    start_upper = round(start_mid + band, 2)
    end_upper = round(end_mid + band, 2)
    start_lower = round(max(0.01, start_mid - band), 2)
    end_lower = round(max(0.01, end_mid - band), 2)
    start_mid_r = round(max(0.02, start_mid), 2)
    end_mid_r = round(max(0.02, end_mid), 2)
    # Keep strict lower < mid < upper ordering even for low-price stocks.
    if start_lower >= start_mid_r:
        start_lower = round(max(0.01, start_mid_r - 0.01), 2)
    if start_upper <= start_mid_r:
        start_upper = round(start_mid_r + 0.01, 2)
    if end_lower >= end_mid_r:
        end_lower = round(max(0.01, end_mid_r - 0.01), 2)
    if end_upper <= end_mid_r:
        end_upper = round(end_mid_r + 0.01, 2)

    slope_pct_per_20d = round(float(slope) * 20.0 / max(end_mid, 1e-6) * 100.0, 2)
    close_now = float(closes[-1])
    width = max(end_upper - end_lower, 1e-6)
    pos_pct = round((close_now - end_lower) / width * 100.0, 1)

    return {
        "available": True,
        "window": win,
        "start_date": _ny_date_str(seg["timestamp"].iloc[0]),
        "end_date": _ny_date_str(seg["timestamp"].iloc[-1]),
        "start_upper": start_upper,
        "end_upper": end_upper,
        "start_mid": start_mid_r,
        "end_mid": end_mid_r,
        "start_lower": start_lower,
        "end_lower": end_lower,
        "slope_pct_per_20d": slope_pct_per_20d,
        "position_pct": pos_pct,
    }


def _classify_elliott_wave(swings: list[dict], trend_dir: str) -> dict:
    """Identify clear Elliott Wave impulse/correction patterns obeying core rules."""
    if len(swings) < 3:
        return {
            "pattern": "consolidating",
            "pattern_label": "波段整理",
            "current_wave": "待确认",
            "phase_label": "拐点数量尚少，先按趋势通道与高低点结构观察",
            "tone": "neutral",
            "confidence": "低",
            "rules_passed": [],
            "fib_targets": [],
        }

    def tag_points(pts: list[dict], labels: list[str]):
        for p, lab in zip(pts, labels):
            p["wave_label"] = lab

    # 1) Complete or active 5-wave UP impulse (L -> H -> L -> H -> L -> H)
    if len(swings) >= 6:
        pts = swings[-6:]
        kinds = [p["kind"] for p in pts]
        p0, p1, p2, p3, p4, p5 = [p["price"] for p in pts]
        if kinds == ["L", "H", "L", "H", "L", "H"]:
            w1, w3, w5 = p1 - p0, p3 - p2, p5 - p4
            if p2 > p0 and p3 > p1 and p4 >= p1 and p5 > p4 and w3 >= min(w1, w5) * 0.98:
                tag_points(pts, ["0", "1", "2", "3", "4", "5"])
                done = pts[-1]["confirmed"]
                return {
                    "pattern": "impulse_up",
                    "pattern_label": "上升五浪推动",
                    "current_wave": "5浪末段" if done else "第5浪推进",
                    "phase_label": (
                        "已完成5浪结构，留意冲高滞涨与A-B-C回撤风险"
                        if done
                        else "处于第5浪冲刺段，上方关注前高延伸并防动量背离"
                    ),
                    "tone": "warning" if done else "positive",
                    "confidence": "高",
                    "rules_passed": [
                        f"浪2(${p2:.2f})不破浪1底(${p0:.2f})",
                        "浪3非最短推动浪",
                        f"浪4(${p4:.2f})未跌入浪1顶(${p1:.2f})区间",
                    ],
                    "fib_targets": [
                        {"label": "5浪等长(1.0×W1)", "price": round(p4 + w1, 2), "ratio": 1.0},
                        {"label": "浪4防守支撑", "price": round(p4, 2), "ratio": 0.0},
                    ],
                }
        if kinds == ["H", "L", "H", "L", "H", "L"]:
            w1, w3, w5 = p0 - p1, p2 - p3, p4 - p5
            if p2 < p0 and p3 < p1 and p4 <= p1 and p5 < p4 and w3 >= min(w1, w5) * 0.98:
                tag_points(pts, ["0", "1", "2", "3", "4", "5"])
                done = pts[-1]["confirmed"]
                return {
                    "pattern": "impulse_down",
                    "pattern_label": "下降五浪推动",
                    "current_wave": "下跌5浪末段" if done else "下跌第5浪",
                    "phase_label": (
                        "五浪下跌结构接近尾声，等待放量站稳再看反弹修复"
                        if done
                        else "处于下跌第5浪释放段，勿盲目抄底，先看止跌信号"
                    ),
                    "tone": "danger",
                    "confidence": "高",
                    "rules_passed": [
                        f"浪2(${p2:.2f})未越浪1顶(${p0:.2f})",
                        "主跌浪3非最短推动浪",
                        f"浪4(${p4:.2f})未越过浪1底(${p1:.2f})",
                    ],
                    "fib_targets": [
                        {"label": "下跌5浪等长参考", "price": round(max(0.01, p4 - w1), 2), "ratio": 1.0},
                        {"label": "浪4反压阻力", "price": round(p4, 2), "ratio": 0.0},
                    ],
                }

    # 2) Wave 4 consolidation in UP or DOWN impulse (5 points)
    if len(swings) >= 5:
        pts = swings[-5:]
        kinds = [p["kind"] for p in pts]
        p0, p1, p2, p3, p4 = [p["price"] for p in pts]
        if kinds == ["L", "H", "L", "H", "L"]:
            w1 = p1 - p0
            if p2 > p0 and p3 > p1 and p4 >= p1:
                tag_points(pts, ["0", "1", "2", "3", "4"])
                return {
                    "pattern": "impulse_up",
                    "pattern_label": "上升推动 · 第4浪",
                    "current_wave": "第4浪休整",
                    "phase_label": f"主升3浪后的强势回踩，未跌破1浪顶 ${p1:.2f}，关注第5浪启动机会",
                    "tone": "positive",
                    "confidence": "高",
                    "rules_passed": [
                        f"浪2(${p2:.2f})不破起涨点(${p0:.2f})",
                        f"浪3(${p3:.2f})突破浪1顶(${p1:.2f})",
                        f"浪4(${p4:.2f})不与浪1重叠",
                    ],
                    "fib_targets": [
                        {"label": "5浪目标(0.618×W1)", "price": round(p4 + 0.618 * w1, 2), "ratio": 0.618},
                        {"label": "5浪目标(1.0×W1)", "price": round(p4 + w1, 2), "ratio": 1.0},
                        {"label": "1浪顶防守位", "price": round(p1, 2), "ratio": 0.0},
                    ],
                }
        if kinds == ["H", "L", "H", "L", "H"]:
            w1 = p0 - p1
            if p2 < p0 and p3 < p1 and p4 <= p1:
                tag_points(pts, ["0", "1", "2", "3", "4"])
                return {
                    "pattern": "impulse_down",
                    "pattern_label": "下降推动 · 第4浪",
                    "current_wave": "下跌第4浪反抽",
                    "phase_label": f"空头主跌后的弱反弹，受制于1浪底 ${p1:.2f} 压力，防范第5浪再下探",
                    "tone": "danger",
                    "confidence": "高",
                    "rules_passed": [
                        f"浪2(${p2:.2f})低于起跌点(${p0:.2f})",
                        f"浪3(${p3:.2f})跌破浪1底(${p1:.2f})",
                        f"反抽浪4(${p4:.2f})未站回浪1底",
                    ],
                    "fib_targets": [
                        {"label": "1浪底反压位", "price": round(p1, 2), "ratio": 0.0},
                        {"label": "5浪下探参考", "price": round(max(0.01, p4 - 0.618 * w1), 2), "ratio": 0.618},
                    ],
                }

    # 3) Active Wave 3 or A-B-C 3-wave correction (4 points)
    if len(swings) >= 4:
        pts = swings[-4:]
        kinds = [p["kind"] for p in pts]
        p0, p1, p2, p3 = [p["price"] for p in pts]
        if kinds == ["L", "H", "L", "H"]:
            w1 = p1 - p0
            if p2 > p0 and p3 > p1:
                if trend_dir == "downtrend":
                    tag_points(pts, ["0", "A", "B", "C"])
                    return {
                        "pattern": "correction_abc",
                        "pattern_label": "空头反弹 A-B-C",
                        "current_wave": "反弹C浪",
                        "phase_label": "主趋势偏弱下的三浪反弹段，靠近通道上轨与等长目标留意获利了结",
                        "tone": "warning",
                        "confidence": "中",
                        "rules_passed": [
                            f"B浪回踩(${p2:.2f})高于起弹点(${p0:.2f})",
                            f"C浪已越过A浪高点(${p1:.2f})",
                        ],
                        "fib_targets": [
                            {"label": "C=1.0×A 等长位", "price": round(p2 + w1, 2), "ratio": 1.0},
                            {"label": "B浪防守位", "price": round(p2, 2), "ratio": 0.0},
                        ],
                    }
                tag_points(pts, ["0", "1", "2", "3"])
                return {
                    "pattern": "impulse_up",
                    "pattern_label": "上升推动 · 第3浪",
                    "current_wave": "第3浪主升",
                    "phase_label": f"已突破1浪高点 ${p1:.2f}，处于主升动能释放段，顺势持有为主",
                    "tone": "positive",
                    "confidence": "高",
                    "rules_passed": [
                        f"浪2(${p2:.2f})守住浪1起点(${p0:.2f})",
                        f"浪3(${p3:.2f})有效突破浪1高点(${p1:.2f})",
                    ],
                    "fib_targets": [
                        {"label": "3浪扩展(1.618×W1)", "price": round(p2 + 1.618 * w1, 2), "ratio": 1.618},
                        {"label": "1浪顶突破支撑", "price": round(p1, 2), "ratio": 0.0},
                    ],
                }
        if kinds == ["H", "L", "H", "L"]:
            wa = p0 - p1
            if p2 < p0 and p3 < p1:
                if trend_dir == "uptrend":
                    tag_points(pts, ["0", "A", "B", "C"])
                    return {
                        "pattern": "correction_abc",
                        "pattern_label": "三浪回调 A-B-C",
                        "current_wave": "调整C浪",
                        "phase_label": "主升趋势中的三浪回撤结构，关注C浪等长支撑与通道下轨企稳信号",
                        "tone": "warning",
                        "confidence": "中",
                        "rules_passed": [
                            f"B浪反抽(${p2:.2f})未越高点(${p0:.2f})",
                            f"C浪(${p3:.2f})跌破A浪低点(${p1:.2f})释放回撤",
                        ],
                        "fib_targets": [
                            {"label": "C=0.618×A 支撑", "price": round(max(0.01, p2 - 0.618 * wa), 2), "ratio": 0.618},
                            {"label": "C=1.0×A 等长支撑", "price": round(max(0.01, p2 - wa), 2), "ratio": 1.0},
                        ],
                    }
                tag_points(pts, ["0", "1", "2", "3"])
                return {
                    "pattern": "impulse_down",
                    "pattern_label": "下降推动 · 第3浪",
                    "current_wave": "下跌第3浪",
                    "phase_label": f"跌破1浪低点 ${p1:.2f}，空头主跌动能占优，优先防守观望",
                    "tone": "danger",
                    "confidence": "高",
                    "rules_passed": [
                        f"浪2(${p2:.2f})低于起跌点(${p0:.2f})",
                        f"浪3(${p3:.2f})跌破浪1低点(${p1:.2f})",
                    ],
                    "fib_targets": [
                        {"label": "下跌3浪(1.618×W1)", "price": round(max(0.01, p2 - 1.618 * wa), 2), "ratio": 1.618},
                        {"label": "1浪底反压位", "price": round(p1, 2), "ratio": 0.0},
                    ],
                }

    # 4) Early Wave 2 pullback or bounce (3 points)
    pts = swings[-3:]
    kinds = [p["kind"] for p in pts]
    p0, p1, p2 = [p["price"] for p in pts]
    if kinds == ["L", "H", "L"] and p2 > p0:
        w1 = p1 - p0
        retrace = (p1 - p2) / max(w1, 1e-6)
        if 0.15 <= retrace <= 0.85:
            tag_points(pts, ["0", "1", "2"])
            return {
                "pattern": "impulse_up",
                "pattern_label": "潜在第2浪回踩",
                "current_wave": "第2浪蓄势",
                "phase_label": f"回撤1浪涨幅的 {retrace * 100:.0f}%，守住起涨点 ${p0:.2f} 上方可关注第3浪突破",
                "tone": "positive" if trend_dir != "downtrend" else "neutral",
                "confidence": "中",
                "rules_passed": [
                    f"回踩低点(${p2:.2f})未破起涨点(${p0:.2f})",
                    f"回撤比例 {retrace * 100:.0f}% 处于常规回调区间",
                ],
                "fib_targets": [
                    {"label": "0.618 黄金分割位", "price": round(p1 - 0.618 * w1, 2), "ratio": 0.618},
                    {"label": "突破确认(1浪顶)", "price": round(p1, 2), "ratio": 1.0},
                    {"label": "3浪测算(1.618×W1)", "price": round(p2 + 1.618 * w1, 2), "ratio": 1.618},
                ],
            }
    if kinds == ["H", "L", "H"] and p2 < p0:
        w1 = p0 - p1
        retrace = (p2 - p1) / max(w1, 1e-6)
        if 0.15 <= retrace <= 0.85:
            tag_points(pts, ["0", "1", "2"])
            return {
                "pattern": "impulse_down",
                "pattern_label": "潜在下跌第2浪反抽",
                "current_wave": "反抽第2浪",
                "phase_label": f"反弹修复跌幅的 {retrace * 100:.0f}%，受压于起跌点 ${p0:.2f} 下方，防再次回落",
                "tone": "warning",
                "confidence": "中",
                "rules_passed": [
                    f"反抽高点(${p2:.2f})未越起跌点(${p0:.2f})",
                    f"反抽比例 {retrace * 100:.0f}% 处于弱势修复区",
                ],
                "fib_targets": [
                    {"label": "0.618 反抽压力", "price": round(p1 + 0.618 * w1, 2), "ratio": 0.618},
                    {"label": "前低破位参考", "price": round(p1, 2), "ratio": 1.0},
                ],
            }

    return {
        "pattern": "consolidating",
        "pattern_label": "箱体整理 / 待定浪",
        "current_wave": "结构整理",
        "phase_label": "当前拐点未形成标准推动或三浪结构，不强行标浪，以高低点与通道上下轨为准",
        "tone": "neutral",
        "confidence": "低",
        "rules_passed": ["未强行套用浪型，保持客观高低点结构"],
        "fib_targets": [],
    }


def compute_wave_trend(frame: pd.DataFrame | None, summary: dict) -> dict:
    """Compute causal Elliott Wave count + Dow/Channel trend structure."""
    tail = _contiguous_regular_tail(frame)
    if len(tail) < 60:
        return _unavailable_wave_trend()

    close = finite(tail["close"].iloc[-1])
    indicators = (summary or {}).get("indicators") or {}
    atr = finite(indicators.get("atr"))
    if atr is None or atr <= 0:
        ranges = (tail["high"] - tail["low"]).tail(14)
        atr = finite(ranges.mean())
    if close is None or close <= 0 or atr is None or atr <= 0:
        return _unavailable_wave_trend("价格或波动率数据无效，暂不识别波浪与趋势结构")

    swings = _causal_swings(tail)
    channel = _compute_trend_channel(tail, atr)

    # Dow Theory structure summary from recent confirmed swings.
    confirmed_h = [s for s in swings if s["kind"] == "H" and s["confirmed"]]
    confirmed_l = [s for s in swings if s["kind"] == "L" and s["confirmed"]]
    recent_struct = [s["structure"] for s in swings[-4:] if s["structure"] in {"HH", "HL", "LH", "LL"}]
    hh_hl = sum(1 for code in recent_struct if code in {"HH", "HL"})
    lh_ll = sum(1 for code in recent_struct if code in {"LH", "LL"})
    dow_bias = 1 if hh_hl > lh_ll else (-1 if lh_ll > hh_hl else 0)

    ma20 = finite(indicators.get("ma20"))
    ma50 = finite(indicators.get("ma50"))
    ma200 = finite(indicators.get("ma200"))
    ma_bias = 0
    if ma20 is not None and ma50 is not None:
        if close > ma50 and ma20 > ma50:
            ma_bias += 1
        elif close < ma50 and ma20 < ma50:
            ma_bias -= 1
    if ma200 is not None:
        if close > ma200:
            ma_bias += 1
        elif close < ma200:
            ma_bias -= 1

    if ma20 is not None and ma50 is not None and ma200 is not None:
        if close > ma20 > ma50 > ma200:
            ma_alignment = "多头排列（价>MA20>MA50>MA200）"
        elif close < ma20 < ma50 < ma200:
            ma_alignment = "空头排列（价<MA20<MA50<MA200）"
        elif close > ma200:
            ma_alignment = "站稳年线（MA200）上方震荡"
        else:
            ma_alignment = "位于年线（MA200）下方整理"
    elif ma20 is not None and ma50 is not None:
        ma_alignment = "中期均线多头（MA20>MA50）" if ma20 > ma50 else "中期均线偏弱（MA20<MA50）"
    else:
        ma_alignment = "长期均线预热中"

    slope_20d = channel.get("slope_pct_per_20d") if channel.get("available") else None
    slope_bias = 1 if slope_20d is not None and slope_20d >= 2.0 else (-1 if slope_20d is not None and slope_20d <= -2.0 else 0)
    total_bias = dow_bias + ma_bias + slope_bias

    if total_bias >= 2:
        direction, dir_label, dir_tone = "uptrend", "上升趋势", "positive"
        structure_text = "多头结构（高点抬高 · 低点抬高）" if dow_bias >= 0 else "偏多通道（均线与斜率向上）"
    elif total_bias <= -2:
        direction, dir_label, dir_tone = "downtrend", "下降趋势", "danger"
        structure_text = "空头结构（高点降低 · 低点降低）" if dow_bias <= 0 else "偏空通道（均线与斜率向下）"
    else:
        direction, dir_label, dir_tone = "sideways", "箱体震荡", "neutral"
        structure_text = "区间整理（高低点交错）"

    pos_pct = channel.get("position_pct") if channel.get("available") else None
    if pos_pct is None:
        pos_label = "通道待确认"
    elif pos_pct < 0:
        pos_label = "跌破通道下轨"
    elif pos_pct <= 25:
        pos_label = "贴近通道下轨支撑"
    elif pos_pct <= 75:
        pos_label = "通道中段运行"
    elif pos_pct <= 100:
        pos_label = "接近通道上轨压力"
    else:
        pos_label = "突破通道上轨"

    breakout_level = confirmed_h[-1]["price"] if confirmed_h else None
    if direction == "downtrend":
        invalidation_level = confirmed_h[-1]["price"] if confirmed_h else None
    else:
        invalidation_level = confirmed_l[-1]["price"] if confirmed_l else None

    wave_info = _classify_elliott_wave(swings, direction)

    # Keep only the recent 12 swings for clean K-line rendering and compact JSON payload.
    visible_pivots = [
        {
            "date": p["date"],
            "price": p["price"],
            "kind": p["kind"],
            "structure": p["structure"],
            "wave_label": p["wave_label"],
            "confirmed": p["confirmed"],
        }
        for p in swings[-12:]
    ]

    if direction == "uptrend":
        if pos_pct is not None and pos_pct <= 30:
            action_guide = (
                f"顺势回踩通道下轨支撑，适合关注低吸节奏；若跌破前低失效位 ${invalidation_level:.2f} 则退出观察。"
                if invalidation_level is not None
                else "顺势回踩通道下轨支撑，适合结合量能关注低吸节奏。"
            )
        elif pos_pct is not None and pos_pct >= 80:
            action_guide = "处于上升通道上沿偏热区，不宜追高，耐心等回踩中轨/下轨或借压力位分批减仓。"
        else:
            action_guide = (
                f"顺势持仓为主，上方关注突破前高 ${breakout_level:.2f}，下方以破前低 ${invalidation_level:.2f} 失效为趋势底线。"
                if breakout_level is not None and invalidation_level is not None
                else "价格位于上升通道中段，顺势跟踪均线支撑与成交量配合。"
            )
    elif direction == "downtrend":
        action_guide = (
            f"空头通道内高点下移，以观望防守或反弹上轨减仓为主；有效站上 ${invalidation_level:.2f} 再看趋势反转。"
            if invalidation_level is not None
            else "处于下降通道内，暂不盲目抄底，等待底部抬高与均线走平。"
        )
    else:
        action_guide = (
            f"箱体区间震荡（参考下沿 ${invalidation_level:.2f} / 上沿 ${breakout_level:.2f}），宜高抛低吸或待放量突破后顺势跟随。"
            if breakout_level is not None and invalidation_level is not None
            else "高低点交错震荡，等待放量突破通道上下轨确认新方向。"
        )

    summary_text = f"{dir_label}（{pos_label}）· {wave_info['pattern_label']}（{wave_info['current_wave']}）"

    return {
        "available": True,
        "reason": "",
        "summary": summary_text,
        "action_guide": action_guide,
        "trend": {
            "direction": direction,
            "label": dir_label,
            "tone": dir_tone,
            "structure": structure_text,
            "structure_code": " → ".join(recent_struct[-4:]) if recent_struct else "待确认",
            "ma_alignment": ma_alignment,
            "slope_pct_per_20d": slope_20d,
            "channel_position_pct": pos_pct,
            "channel_position_label": pos_label,
            "breakout_level": breakout_level,
            "invalidation_level": invalidation_level,
            "channel": channel,
        },
        "wave": {
            **wave_info,
            "pivots": visible_pivots,
        },
        "disclaimer": WAVE_DISCLAIMER,
    }
