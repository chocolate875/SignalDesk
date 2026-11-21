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
    }


def _contiguous_regular_tail(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    reg = frame[frame["session"] == "regular"] if "session" in frame.columns else frame
    if reg.empty:
        return pd.DataFrame()
    valid = reg["close"].notna() & np.isfinite(reg["close"]) & (reg["close"] > 0)
    if valid.empty or not bool(valid.iloc[-1]):
        return pd.DataFrame()
    breaks = (~valid).cumsum()
    return reg[breaks == breaks.iloc[-1]]


def _pick_anchor(
    candidates: list[tuple[str, float]], low: float, high: float, target: float, fallback: float
) -> tuple[float, str | None]:
    in_range = [(name, val) for name, val in candidates if val is not None and low <= val <= high]
    if in_range:
        chosen_name, chosen_val = min(in_range, key=lambda item: abs(item[1] - target))
        return chosen_val, f"{chosen_name} ${chosen_val:.2f}"
    return fallback, None


def compute_forecast(
    frame: pd.DataFrame | None,
    summary: dict,
    research: dict,
    long_plan: dict,
    instrument: dict | None = None,
    fund_metrics: dict | None = None,
) -> dict:
    """Compute causal support/resistance price levels and a 5-tier rating."""
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
    ema20 = finite(indicators.get("ema20"))
    bb_lower = finite(indicators.get("bb_lower"))
    bb_middle = finite(indicators.get("bb_middle"))
    bb_upper = finite(indicators.get("bb_upper"))
    rsi = finite(indicators.get("rsi"))

    pivot = (high_20 + low_20 + close) / 3.0
    s1 = 2.0 * pivot - high_20
    r1 = 2.0 * pivot - low_20
    fib_ext = high_20 + 0.618 * max(0.0, high_20 - low_20)

    # 1) Buy high (light entry / pullback watch)
    bh_candidates = [
        (name, val)
        for name, val in [
            ("MA20 均线", ma20),
            ("EMA20 均线", ema20),
            ("布林中轨", bb_middle),
            ("MA50 均线", ma50),
            ("MA200 年线", ma200),
            ("枢轴支撑 S1", s1),
            ("20日低点", low_20),
        ]
        if val is not None
    ]
    bh_fallback = max(
        0.03,
        close - (0.45 * atr if rsi is not None and rsi <= 35 else 0.75 * atr),
    )
    bh_raw, bh_anchor = _pick_anchor(
        bh_candidates, max(0.03, close - 1.5 * atr), close, close - 0.55 * atr, bh_fallback
    )
    bh_raw = min(close, max(0.03, bh_raw))

    # 2) Buy low (deeper support)
    bl_candidates = [
        (name, val)
        for name, val in [
            ("MA50 支撑", ma50),
            ("MA200 支撑", ma200),
            ("布林下轨", bb_lower),
            ("20日低点", low_20),
            ("60日低点", low_60),
            ("枢轴支撑 S1", s1),
        ]
        if val is not None
    ]
    bl_low_bound = max(0.02, min(bh_raw - 0.02, close - 3.2 * atr))
    bl_high_bound = max(bl_low_bound, bh_raw - 0.45 * atr)
    bl_fallback = max(0.02, min(bl_high_bound, bh_raw - 1.1 * atr))
    bl_raw, bl_anchor = _pick_anchor(
        bl_candidates, bl_low_bound, bl_high_bound, bh_raw - 1.1 * atr, bl_fallback
    )

    # 3) Stop loss (defensive level below buy zone)
    stop_candidate = min(bl_raw - 0.8 * atr, low_20 - 0.4 * atr)
    stop_floor = max(0.01, min(bl_raw - 0.02, bl_raw - 2.2 * atr))
    stop_ceil = max(stop_floor, min(bl_raw - 0.01, bl_raw - 0.5 * atr))
    stop_raw = min(stop_ceil, max(stop_floor, stop_candidate))

    # 4) First sell target (partial take-profit / resistance)
    sl_candidates = [
        (name, val)
        for name, val in [
            ("20日高点压力", high_20),
            ("布林上轨", bb_upper),
            ("枢轴阻力 R1", r1),
            ("MA20 压力", ma20),
            ("MA50 压力", ma50),
            ("MA200 压力", ma200),
        ]
        if val is not None
    ]
    sl_raw, sl_anchor = _pick_anchor(
        sl_candidates, close + 0.9 * atr, close + 3.2 * atr, close + 1.8 * atr, close + 1.8 * atr
    )

    # 5) Second sell target (swing resistance)
    sh_candidates = [
        (name, val)
        for name, val in [
            ("60日高点阻力", high_60),
            ("布林上轨", bb_upper),
            ("枢轴阻力 R1", r1),
            ("MA200 压力", ma200),
            ("斐波那契 1.618 扩展", fib_ext),
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
    buy_anchors = list(dict.fromkeys(buy_anchors))[:3]

    sell_anchors = [
        sl_anchor or f"ATR14 一卖 ${sell_low:.2f}",
        sh_anchor or f"ATR14 二卖 ${sell_high:.2f}",
    ]
    sell_anchors = list(dict.fromkeys(sell_anchors))[:3]

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

    # 5-tier Rating calculation (个股 vs ETF/指数基金分流评估)
    tech_score = float(summary["score"])
    state_label = {"strong": "结构偏强", "weak": "结构偏弱", "neutral": "结构中性"}.get(
        summary.get("state", "neutral"), "待确认"
    )

    inst = instrument or {}
    is_fund = bool(inst.get("is_fund"))
    is_leveraged = bool(inst.get("is_leveraged"))
    is_inverse = bool(inst.get("is_inverse"))
    fm = fund_metrics or {}

    val = research.get("valuation") or {}
    val_fresh = bool(val.get("fresh"))
    curve = research.get("curve") or {}
    curve_fresh = bool(curve.get("fresh"))
    ten_change_bp = finite(curve.get("ten_change_bp"))
    pe = finite(val.get("pe_ttm"))
    div = finite(val.get("dividend_yield_pct")) or 0.0
    gap = finite(research.get("yield_gap_pp"))

    rr_score = float(
        np.clip(
            30.0 + risk_reward_ratio * 25.0 + (8.0 if buy_discount_pct >= -2.0 else 0.0),
            15.0,
            95.0,
        )
    )
    rr_detail = f"现价盈亏比 {risk_reward_ratio:.2f}:1（距参考买点 {buy_discount_pct:+.1f}%）"

    risks = list(summary.get("risks") or [])
    rc_score = 85.0
    if "波动偏高" in risks:
        rc_score -= 12.0
    if "偏离MA20超过2ATR" in risks:
        rc_score -= 12.0
    if "RSI进入极值区" in risks:
        rc_score -= 15.0 if rsi is not None and rsi >= 70 else 6.0
    if any("过期" in r for r in risks):
        rc_score -= 8.0

    hv60 = finite(fm.get("hv60_pct"))
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

        if is_leveraged and hv60 is not None:
            if hv60 >= 75.0:
                rc_score -= 18.0
            elif hv60 >= 55.0:
                rc_score -= 10.0
            elif hv60 >= 40.0:
                rc_score -= 5.0
        elif hv60 is not None and hv60 >= 45.0:
            rc_score -= 6.0

        rc_score = max(10.0, rc_score)
        if is_leveraged:
            vol_text = f"年化波动 {hv60:.1f}%（存在杠杆损耗）" if hv60 is not None else "日度再平衡杠杆损耗"
            rc_detail = f"{vol_text} · 风险 {len(risks)} 项" if risks else vol_text
            raw_factors = [
                {"key": "technical", "label": "技术结构", "base_weight": 0.45, "score": tech_score, "detail": f"日线评分 {tech_score:.1f}（{state_label}）"},
                {"key": "fund_position", "label": "波动与回撤", "base_weight": 0.20, "score": fund_pos_score, "detail": fund_pos_detail},
                {"key": "risk_reward", "label": "点位赔率", "base_weight": 0.20, "score": rr_score, "detail": rr_detail},
                {"key": "risk_control", "label": "杠杆风控", "base_weight": 0.15, "score": rc_score, "detail": rc_detail},
            ]
        else:
            rc_detail = (
                f"年化波动 {hv60:.1f}% · 风险 {len(risks)} 项"
                if hv60 is not None and risks
                else (f"年化波动 {hv60:.1f}% · 无额外技术风险" if hv60 is not None else (f"独立风险提示 {len(risks)} 项" if risks else "无额外技术风险标记"))
            )
            raw_factors = [
                {"key": "technical", "label": "技术结构", "base_weight": 0.40, "score": tech_score, "detail": f"日线评分 {tech_score:.1f}（{state_label}）"},
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
                val_score = float(np.clip(58.0 + gap * 10.0 + (4.0 if div >= 2.0 else 0.0), 15.0, 95.0))
                val_detail = f"PE {pe:.1f}x，股债利差 {gap:+.2f}pp"
            elif pe is not None and pe > 0:
                val_score = float(np.clip(90.0 - pe * 1.15 + (4.0 if div >= 2.0 else 0.0), 20.0, 82.0))
                val_detail = f"PE {pe:.1f}x（缺有效美债利率对照，按市盈率水平估算）"
            else:
                val_score = None
                val_detail = "暂无有效市盈率，权重按其余维度归一化"
        else:
            val_score = None
            val_detail = "估值数据未更新或已过期，权重按其余维度归一化"

        rc_score = max(10.0, rc_score)
        rc_detail = f"独立风险提示 {len(risks)} 项" if risks else "无额外技术风险标记"
        raw_factors = [
            {"key": "technical", "label": "技术结构", "base_weight": 0.40, "score": tech_score, "detail": f"日线评分 {tech_score:.1f}（{state_label}）"},
            {"key": "valuation", "label": "估值利率", "base_weight": 0.30, "score": val_score, "detail": val_detail},
            {"key": "risk_reward", "label": "点位赔率", "base_weight": 0.20, "score": rr_score, "detail": rr_detail},
            {"key": "risk_control", "label": "风险控制", "base_weight": 0.10, "score": rc_score, "detail": rc_detail},
        ]

    active_weight = sum(f["base_weight"] for f in raw_factors if f["score"] is not None)
    factors = []
    raw_score = 0.0
    for item in raw_factors:
        eff_weight = item["base_weight"] / active_weight if item["score"] is not None else 0.0
        if item["score"] is not None:
            raw_score += item["score"] * eff_weight
        factors.append(
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

    if is_inverse:
        cap_tier("hold")
        guardrails.append("属于反向做空杠杆工具，存在每日再平衡损耗，仅作短线对冲参考，暂不出具买入评级")
    elif is_leveraged:
        cap_tier("buy")
        guardrails.append("属于高倍杠杆交易型基金，存在每日复利波动损耗，仅适合波段跟踪并须严守止损")

    stale_risk = any("过期" in r for r in risks)
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

    label, tone, stars = TIER_SPECS[code]
    guard_note = f"（已触发风控护栏：{guardrails[0]}）" if guardrails else ""
    rating_summary = (
        f"综合评级「{label}」（{raw_score:.1f}分，置信度{confidence}）："
        f"参考买点 ${buy_low:.2f}–${buy_high:.2f}，第一卖点 ${sell_low:.2f}，"
        f"现价盈亏比 {risk_reward_ratio:.2f}:1{guard_note}。"
    )

    return {
        "levels": levels,
        "rating": {
            "available": True,
            "code": code,
            "label": label,
            "tone": tone,
            "score": raw_score,
            "stars": stars,
            "confidence": confidence,
            "summary": rating_summary,
            "factors": factors,
            "guardrails": guardrails,
            "disclaimer": ETF_DISCLAIMER if is_fund else DISCLAIMER,
        },
    }
