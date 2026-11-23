"""夜盘、盘前与盘后独立行情汇总及流动性过滤跳空预警引擎。

设计红线：
- 盘外（夜盘/盘前/盘后）行情仅作独立展示、开盘前跳空预警与 Codex 手动复核背景；
- 绝不混入常规时段日线 K 线、技术指标、波浪结构、点位预测或 5 级买卖评级；
- 必须结合盘外成交额做流动性门控，防止薄流动性小单毛刺误报高危预警。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .calendar import NY
from .indicators import finite

EXTENDED_RULE_VERSION = "ext-1.0.0"

# 盘外流动性与跳空阈值
LIQUID_TURNOVER_USD = 1_000_000.0        # >= 100 万美元视为流动性充分
ACTIVE_TURNOVER_USD = 20_000_000.0       # >= 2,000 万美元视为放量活跃
GAP_SIGNIFICANT_PCT = 3.0                # >= ±3% 显著跳空
GAP_MAJOR_PCT = 6.0                      # >= ±6% 大幅跳空

SESSION_LABELS: dict[str, str] = {
    "overnight": "夜盘",
    "pre": "盘前",
    "post": "盘后",
}

EXTENDED_DISCLAIMER = (
    "盘外（夜盘/盘前/盘后）流动性低于常规盘，仅作开盘前跳空参考与预案预警，不计入日线K线、技术评分、波浪结构与5级评级。"
)


def _parse_iso(ts: Any) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=NY)
    except ValueError:
        return None


def _format_usd_cn(amount: float | None) -> str:
    if amount is None or amount < 0:
        return "—"
    if amount >= 1e8:
        return f"${amount / 1e8:.2f}亿"
    if amount >= 1e4:
        return f"${amount / 1e4:.0f}万"
    return f"${amount:,.0f}"


def _liquidity_meta(turnover: float | None) -> tuple[bool, str]:
    if turnover is None or turnover <= 0:
        return False, "无成交额"
    if turnover >= ACTIVE_TURNOVER_USD:
        return True, "放量充分"
    if turnover >= LIQUID_TURNOVER_USD:
        return True, "成交活跃"
    return False, "成交偏薄"


def _normalize_session_entry(
    session_key: str,
    raw: dict[str, Any] | None,
    fallback_ref_close: float | None,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    price = finite(raw.get("last"))
    if price is None or price <= 0:
        return None
    ref_close = finite(raw.get("prev_close"))
    if ref_close is None or ref_close <= 0:
        ref_close = fallback_ref_close
    gap_pct = (
        round((price / ref_close - 1.0) * 100.0, 2)
        if ref_close is not None and ref_close > 0
        else None
    )
    high = finite(raw.get("high"))
    low = finite(raw.get("low"))
    volume_raw = finite(raw.get("volume"))
    volume = int(volume_raw) if volume_raw is not None and volume_raw >= 0 else None
    turnover = finite(raw.get("turnover"))
    if turnover is not None and turnover < 0:
        turnover = None
    stamp = _parse_iso(raw.get("timestamp"))
    liquid, liq_label = _liquidity_meta(turnover)
    return {
        "session": session_key,
        "label": SESSION_LABELS.get(session_key, session_key),
        "price": round(price, 4),
        "ref_close": round(ref_close, 4) if ref_close is not None else None,
        "gap_pct": gap_pct,
        "high": round(high, 4) if high is not None and high > 0 else None,
        "low": round(low, 4) if low is not None and low > 0 else None,
        "volume": volume,
        "turnover": round(turnover, 2) if turnover is not None else None,
        "turnover_text": _format_usd_cn(turnover),
        "timestamp": stamp.isoformat() if stamp is not None else None,
        "_dt": stamp,
        "liquid": liquid,
        "liquidity_label": liq_label,
    }


def summarize_extended_hours(
    quote: dict[str, Any] | None,
    market: dict[str, Any] | None,
    long_plan: dict[str, Any] | None,
    wave_trend: dict[str, Any] | None,
    forecast: dict[str, Any] | None,
    now: datetime,
    demo: bool = False,
) -> dict[str, Any]:
    """汇总夜盘/盘前/盘后独立报价并生成带流动性门控的前置预警。"""
    q = quote or {}
    ext_map = q.get("extended") if isinstance(q.get("extended"), dict) else {}
    regular_last = finite(q.get("last"))
    regular_dt = _parse_iso(q.get("timestamp"))
    market_session = str((market or {}).get("session") or "closed")

    normalized: dict[str, dict[str, Any]] = {}
    for key in ("overnight", "pre", "post"):
        entry = _normalize_session_entry(key, ext_map.get(key), regular_last)
        if entry is not None:
            normalized[key] = entry

    if not normalized:
        return {
            "available": False,
            "is_live_session": False,
            "rule_version": EXTENDED_RULE_VERSION,
            "source": "合成盘外" if demo else "LongPort 盘外",
            "active_session": None,
            "active_label": None,
            "price": None,
            "ref_close": None,
            "gap_pct": None,
            "high": None,
            "low": None,
            "volume": None,
            "turnover": None,
            "turnover_text": "—",
            "timestamp": None,
            "liquid": False,
            "liquidity_label": "无数据",
            "alert_level": "none",
            "badge": "",
            "headline": "",
            "triggers": [],
            "sessions": {},
            "disclaimer": EXTENDED_DISCLAIMER,
        }

    # 仅认为时间戳严格晚于最近常规收盘/报价的盘外分段为「当前盘外有效数据」
    fresh_candidates: dict[str, dict[str, Any]] = {}
    for key, entry in normalized.items():
        dt = entry["_dt"]
        if dt is None:
            continue
        # 不接受未来时间（允许 120s 钟差）
        if (dt - now).total_seconds() > 120:
            continue
        if regular_dt is None or dt > regular_dt:
            fresh_candidates[key] = entry

    # 选择主展示时段：
    # - 常规盘中：盘外非实时主段，仅保留今晨盘前或最新盘外作为参考（不触发实时盘外预警）
    # - 盘外/休市：优先匹配当前市场时段，其次选择时间戳最新的有效盘外段
    active: dict[str, Any] | None = None
    is_live_session = False

    if market_session == "regular":
        if "pre" in normalized:
            active = normalized["pre"]
        else:
            valid_dt = [e for e in normalized.values() if e["_dt"] is not None]
            active = max(valid_dt, key=lambda x: x["_dt"]) if valid_dt else next(iter(normalized.values()))
        is_live_session = False
    else:
        if market_session in fresh_candidates:
            active = fresh_candidates[market_session]
            is_live_session = True
        elif fresh_candidates:
            active = max(fresh_candidates.values(), key=lambda x: x["_dt"])
            is_live_session = True
        else:
            valid_dt = [e for e in normalized.values() if e["_dt"] is not None]
            active = max(valid_dt, key=lambda x: x["_dt"]) if valid_dt else next(iter(normalized.values()))
            is_live_session = False

    price = active["price"]
    gap_pct = active["gap_pct"]
    liquid = bool(active["liquid"])
    label = active["label"]
    turnover_text = active["turnover_text"]

    triggers: list[str] = []
    alert_level = "none"

    if is_live_session and gap_pct is not None:
        abs_gap = abs(gap_pct)
        if abs_gap >= GAP_MAJOR_PCT:
            triggers.append(
                f"{label}大幅{'高开' if gap_pct > 0 else '低开'} {gap_pct:+.2f}%（成交额 {turnover_text}）"
            )
            alert_level = "positive" if gap_pct > 0 else "danger"
        elif abs_gap >= GAP_SIGNIFICANT_PCT:
            triggers.append(
                f"{label}显著{'高开' if gap_pct > 0 else '低开'} {gap_pct:+.2f}%（成交额 {turnover_text}）"
            )
            alert_level = "positive" if gap_pct > 0 else "warning"

        # 关键价位前置预检（个人计划价、波浪失效/反转位、预测买卖点）
        lp = long_plan or {}
        stop_price = finite(lp.get("stop"))
        target_price = finite(lp.get("target"))
        reg_close = finite(lp.get("close")) or active["ref_close"]

        if stop_price is not None and price <= stop_price:
            if reg_close is None or reg_close > stop_price:
                triggers.append(f"{label}价 ${price:.2f} 已跌破计划失效价 ${stop_price:.2f}，留意开盘防守")
            else:
                triggers.append(f"{label}价 ${price:.2f} 仍位于计划失效价 ${stop_price:.2f} 下方")
            alert_level = "danger"
        elif target_price is not None and price >= target_price:
            if reg_close is None or reg_close < target_price:
                triggers.append(f"{label}价 ${price:.2f} 已触及计划目标价 ${target_price:.2f}，可提前评估止盈预案")
            else:
                triggers.append(f"{label}价 ${price:.2f} 延续高于计划目标价 ${target_price:.2f}")
            if alert_level not in {"danger"}:
                alert_level = "warning"

        wt_trend = (wave_trend or {}).get("trend") or {}
        inv_level = finite(wt_trend.get("invalidation_level"))
        wt_dir = str(wt_trend.get("direction") or "")
        if inv_level is not None and inv_level > 0:
            if wt_dir == "downtrend" and price >= inv_level and (reg_close is None or reg_close < inv_level):
                triggers.append(f"{label}价 ${price:.2f} 站上波浪前高反转位 ${inv_level:.2f}，关注开盘能否确认反转")
                if alert_level == "none":
                    alert_level = "positive"
            elif wt_dir != "downtrend" and price <= inv_level and (reg_close is None or reg_close > inv_level):
                triggers.append(f"{label}价 ${price:.2f} 跌破波浪前低失效位 ${inv_level:.2f}，警惕开盘破坏多头结构")
                if alert_level != "danger":
                    alert_level = "warning"

        fc_levels = (forecast or {}).get("levels") or {}
        if fc_levels.get("available"):
            buy_low = finite(fc_levels.get("buy_low"))
            buy_high = finite(fc_levels.get("buy_high"))
            sell_low = finite(fc_levels.get("sell_low"))
            if (
                buy_low is not None
                and buy_high is not None
                and buy_low <= price <= buy_high
                and reg_close is not None
                and reg_close > buy_high
            ):
                triggers.append(f"{label}回踩进入参考买点区间（${buy_low:.2f}–${buy_high:.2f}）")
                if alert_level == "none":
                    alert_level = "info"
            elif (
                sell_low is not None
                and price >= sell_low
                and reg_close is not None
                and reg_close < sell_low
            ):
                triggers.append(f"{label}跃升触及参考卖点压力区（≥ ${sell_low:.2f}）")
                if alert_level == "none":
                    alert_level = "info"

        # 流动性门控：盘外成交额不足 100 万美元时，绝不出高危/强警报，降级为 info 并显式警示
        if not liquid:
            if triggers:
                triggers.append(f"当前{label}成交额仅 {turnover_text}（< $100万，流动性偏薄），开盘易回吐，谨防小单虚晃")
            if alert_level in {"danger", "warning", "positive"}:
                alert_level = "info"

    # 生成精简 badge 与一句大白话 headline
    if gap_pct is not None:
        badge = f"{label} {gap_pct:+.1f}%"
    else:
        badge = f"{label} ${price:.2f}"

    if is_live_session:
        if triggers:
            headline = triggers[0]
        elif gap_pct is not None:
            liq_suffix = f"成交额 {turnover_text}（{active['liquidity_label']}）"
            headline = f"{label}报价 ${price:.2f}（较常规收盘 {gap_pct:+.2f}%），{liq_suffix}，暂未触发显著跳空或关键价穿越。"
        else:
            headline = f"{label}报价 ${price:.2f}，成交额 {turnover_text}。"
    else:
        if gap_pct is not None:
            headline = f"最近{label}参考价 ${price:.2f}（{gap_pct:+.2f}%，成交额 {turnover_text}）；当前处于常规盘中，以盘中主价为准。"
        else:
            headline = f"最近{label}参考价 ${price:.2f}（成交额 {turnover_text}）。"

    # 清理内部 _dt 后输出按时间顺序排列的分段记录（夜盘 -> 盘前 -> 盘后）
    clean_sessions: dict[str, dict[str, Any]] = {}
    for key in ("overnight", "pre", "post"):
        if key in normalized:
            item = {k: v for k, v in normalized[key].items() if k != "_dt"}
            item["is_fresh"] = key in fresh_candidates
            clean_sessions[key] = item

    return {
        "available": True,
        "is_live_session": is_live_session,
        "rule_version": EXTENDED_RULE_VERSION,
        "source": "合成盘外" if demo else "LongPort 盘外",
        "active_session": active["session"],
        "active_label": label,
        "price": price,
        "ref_close": active["ref_close"],
        "gap_pct": gap_pct,
        "high": active["high"],
        "low": active["low"],
        "volume": active["volume"],
        "turnover": active["turnover"],
        "turnover_text": turnover_text,
        "timestamp": active["timestamp"],
        "liquid": liquid,
        "liquidity_label": active["liquidity_label"],
        "alert_level": alert_level,
        "badge": badge,
        "headline": headline,
        "triggers": triggers,
        "sessions": clean_sessions,
        "disclaimer": EXTENDED_DISCLAIMER,
    }
