"""Deterministic synthetic fixtures. No downloaded market prices, no real holdings."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .calendar import NY, bar_end, calendar, regular_intervals
from .markets import US, market_for
from .models import Allocation
from .research import curve_summary

DEMO_BENCHMARKS: dict[str, tuple[float, float]] = {
    "SPY.US": (595.0, 0.00045),
    "QQQ.US": (515.0, 0.00060),
    "RSP.US": (182.0, 0.00038),
    "IWM.US": (228.0, 0.00032),
    "HYG.US": (79.5, 0.00018),
    "IEF.US": (94.2, 0.00004),
}

DEMO_NAMES = [
    ("NVDA.US", "英伟达", 142.8, 12, 8, 0.0012),
    ("AAPL.US", "苹果", 232.4, 24, 0, 0.0007),
    ("MSFT.US", "微软", 427.6, 12, 0, 0.0004),
    ("GOOGL.US", "谷歌", 178.2, 20, 0, -0.0003),
    ("AMZN.US", "亚马逊", 204.3, 16, 0, 0.0002),
    ("META.US", "Meta", 582.5, 0, 6, -0.0010),
    ("TSLA.US", "特斯拉", 268.7, 0, 10, -0.0014),
    ("AMD.US", "超威半导体", 153.6, 0, 14, 0.0009),
    ("00700.HK", "腾讯控股", 420.0, 0, 0, 0.0005),
    ("600519.SH", "贵州茅台", 1450.0, 0, 0, 0.0003),
    ("000001.SZ", "平安银行", 11.5, 0, 0, 0.0002),
]


DEMO_PLANS = {
    "NVDA.US": {
        "favorite": True,
        "groups": ["AI 与算力", "核心科技"],
        "stop": 128.0,
        "target": 160.0,
    },
    "AAPL.US": {
        "favorite": True,
        "groups": ["核心科技"],
        "stop": 215.0,
        "target": 250.0,
    },
    "MSFT.US": {
        "favorite": False,
        "groups": ["AI 与算力", "核心科技"],
        "stop": 395.0,
        "target": 465.0,
    },
    "GOOGL.US": {"favorite": False, "groups": ["核心科技"]},
    "AMZN.US": {"favorite": False, "groups": []},
    "META.US": {"favorite": False, "groups": ["核心科技", "成长观察"]},
    "TSLA.US": {
        "favorite": False,
        "groups": ["成长观察"],
        "stop": 240.0,
        "target": 300.0,
    },
    "00700.HK": {"groups": ["港股观察"]},
    "600519.SH": {"groups": ["沪深观察"]},
    "000001.SZ": {"groups": ["沪深观察"]},
    "AMD.US": {"favorite": False, "groups": ["AI 与算力", "成长观察"]},
}


def allocations() -> list[Allocation]:
    items = []
    for index, (symbol, name, price, long_qty, q, _) in enumerate(DEMO_NAMES):
        held = index < 5
        qty = float(long_qty + q) if held else 0.0
        plan = DEMO_PLANS.get(symbol, {})
        groups = list(plan.get("groups", []))
        items.append(
            Allocation(
                symbol=symbol,
                name=name,
                long_quantity=qty,
                broker_quantity=qty,
                available_quantity=qty,
                cost_price=round(price * 0.93, 2) if held else None,
                watch_only=not held,
                watch_sleeve="long",
                long_stop_price=plan.get("stop"),
                long_target_price=plan.get("target"),
                favorite=bool(plan.get("favorite", False)),
                in_watchlist=bool(groups),
                watchlist_groups=groups,
                manual_watch=not held and not groups,
            )
        )
    return items


def watchlist_groups() -> list[dict]:
    grouped: dict[str, list[str]] = {}
    for item in allocations():
        for group_name in item.watchlist_groups:
            grouped.setdefault(group_name, []).append(item.symbol)
    return [
        {"id": index + 1, "name": name, "symbols": symbols}
        for index, (name, symbols) in enumerate(grouped.items())
    ]


def yield_curve(last_close: datetime) -> dict:
    end = pd.Timestamp(last_close.astimezone(NY).date())
    days = calendar().sessions_in_range(end - pd.Timedelta(days=45), end)[-22:]
    observations = {
        day.date().isoformat(): (3.7, 4.1 - (len(days) - 1 - i) * 0.01, 3.85)
        for i, day in enumerate(days)
    }
    return curve_summary(observations)


def comex_gold(last_close: datetime) -> dict:
    """为演示模式生成确定性的合成 COMEX 黄金主力参考行情（不代表真实市场）。"""
    end = pd.Timestamp(last_close.astimezone(NY).date())
    days = calendar().sessions_in_range(end - pd.Timedelta(days=45), end)[-22:]
    as_of = days[-1].date().isoformat() if len(days) else last_close.astimezone(NY).date().isoformat()
    prior_date = days[0].date().isoformat() if len(days) >= 22 else None
    price = 2684.50
    prev_close = 2662.20
    prior_close = 2602.50
    return {
        "symbol": "GC=F",
        "name": "COMEX 黄金主力",
        "exchange": "COMEX",
        "currency": "USD",
        "unit": "美元/盎司",
        "price": price,
        "prev_close": prev_close,
        "change_pct": round((price / prev_close - 1.0) * 100.0, 2),
        "day_high": 2692.40,
        "day_low": 2655.80,
        "prior_date": prior_date,
        "change_21d_pct": round((price / prior_close - 1.0) * 100.0, 2) if prior_date else None,
        "as_of": as_of,
        "quote_time": last_close.isoformat(),
        "fetched_at": last_close.isoformat(),
        "source": "合成期金",
    }


def demo_extended_quote(symbol: str, regular_close: float, regular_end: datetime, now: datetime) -> dict:
    """为演示模式生成确定性的合成夜盘/盘前报价，用于离线展示盘外跳空与流动性门控效果。"""
    presets: dict[str, tuple[float, float, float]] = {
        "NVDA.US": (0.036, 0.044, 68_500_000.0),   # 盘前放量显著高开
        "AAPL.US": (0.008, 0.011, 24_200_000.0),   # 温和波动
        "TSLA.US": (-0.034, -0.041, 52_000_000.0), # 盘前放量低开
        "AMD.US": (0.035, 0.039, 420_000.0),       # 成交偏薄（< $100万，测试流动性门控降级）
    }
    if symbol not in presets or regular_close <= 0:
        return {}
    ov_gap, pre_gap, turnover = presets[symbol]
    # 仅生成严格晚于常规收盘且不晚于当前时刻的合成时间戳
    if now <= regular_end:
        return {}
    pre_ts = min(now, regular_end + timedelta(hours=12))
    ov_ts = min(pre_ts - timedelta(minutes=30), regular_end + timedelta(hours=6))
    if ov_ts <= regular_end:
        ov_ts = regular_end + timedelta(seconds=10)
    if pre_ts <= ov_ts:
        pre_ts = min(now, ov_ts + timedelta(seconds=10))
    ov_price = round(regular_close * (1.0 + ov_gap), 2)
    pre_price = round(regular_close * (1.0 + pre_gap), 2)
    return {
        "overnight": {
            "last": ov_price,
            "prev_close": round(regular_close, 2),
            "high": round(ov_price * 1.006, 2),
            "low": round(ov_price * 0.994, 2),
            "volume": int(turnover * 0.6 / max(ov_price, 1.0)),
            "turnover": round(turnover * 0.6, 2),
            "timestamp": ov_ts.isoformat(),
        },
        "pre": {
            "last": pre_price,
            "prev_close": round(regular_close, 2),
            "high": round(pre_price * 1.008, 2),
            "low": round(pre_price * 0.992, 2),
            "volume": int(turnover / max(pre_price, 1.0)),
            "turnover": round(turnover, 2),
            "timestamp": pre_ts.isoformat(),
        },
    }


def make_benchmark_bars(symbol: str, now: datetime) -> list[dict]:
    """为全市场基准 ETF（SPY/QQQ/RSP/IWM/HYG/IEF）生成确定性常规日线，独立于演示自选股。"""
    base, drift = DEMO_BENCHMARKS.get(symbol, (100.0, 0.0003))
    seed = 7100 + sum((idx + 1) * ord(ch) for idx, ch in enumerate(symbol))
    rng = np.random.default_rng(seed)
    cal = calendar()
    end_day = pd.Timestamp(now.astimezone(NY).date())
    days = cal.sessions_in_range(end_day - pd.Timedelta(days=620), end_day)
    clocks = []
    for day in days[-340:]:
        ts = cal.session_open(day).to_pydatetime()
        if bar_end(ts, "day") <= now:
            clocks.append((ts, "regular"))
    count = len(clocks)
    if count == 0:
        return []
    noise = rng.normal(0, 0.0055, count)
    slopes = drift + noise
    slopes[-65:] = drift * 1.4 + noise[-65:] * 0.4
    closes = np.exp(np.cumsum(slopes))
    closes *= base / closes[-1]
    result = []
    for i, (ts, session) in enumerate(clocks):
        closing = float(closes[i])
        opening = float(closes[i - 1] if i else closes[i] * 0.999)
        width = closing * rng.uniform(0.001, 0.0035)
        volume = int(rng.integers(5_000_000, 40_000_000))
        result.append(
            {
                "timestamp": ts.astimezone(pd.Timestamp.now(tz="UTC").tz).isoformat(),
                "session": session,
                "open": opening,
                "close": closing,
                "high": max(opening, closing) + width,
                "low": min(opening, closing) - width,
                "volume": volume,
                "turnover": float(volume * closing),
                "confirmed": True,
            }
        )
    return result


def make_bars(symbol: str, timeframe: str, now: datetime) -> list[dict]:
    n = (
        next(i for i, item in enumerate(DEMO_NAMES) if item[0] == symbol)
        if symbol in {x[0] for x in DEMO_NAMES}
        else 1
    )
    _, _, base, _, _, drift = DEMO_NAMES[n]
    rng = np.random.default_rng(2000 + n + (0 if timeframe == "day" else 100))
    venue = market_for(symbol)
    cal = calendar(venue)
    end_day = min(pd.Timestamp(now.astimezone(venue.timezone).date()), cal.last_session)
    days = cal.sessions_in_range(max(cal.first_session, end_day - pd.Timedelta(days=1500 if timeframe == "day" else 55)), end_day)
    clocks = []
    if timeframe == "day":
        for day in days[-1000:]:
            ts = cal.session_open(day).to_pydatetime()
            if bar_end(ts, "day", venue) <= now:
                clocks.append((ts, "regular"))
    else:
        for day in days[-32:]:
            if venue != US:
                bounds = [(start, finish, "regular") for start, finish in regular_intervals(cal, day)]
            else:
                midnight = datetime.combine(day.date(), datetime.min.time(), NY)
                close = cal.session_close(day).to_pydatetime()
                bounds = [
                    (midnight - timedelta(hours=4), midnight + timedelta(hours=4), "overnight"),
                    (midnight + timedelta(hours=4), midnight + timedelta(hours=9, minutes=30), "pre"),
                    (cal.session_open(day).to_pydatetime(), close, "regular"),
                    (close, midnight + timedelta(hours=17 if close.astimezone(NY).hour < 16 else 20), "post"),
                ]
            for start, finish, session in bounds:
                while start + timedelta(minutes=15) <= finish and start + timedelta(minutes=15) <= now:
                    clocks.append((start, session))
                    start += timedelta(minutes=15)
    count = len(clocks)
    noise = rng.normal(0, 0.004 if timeframe == "day" else 0.0018, count)
    slopes = drift * (1 if timeframe == "day" else 0.35) + noise
    # Recent persistent direction makes synthetic scenarios visually and numerically distinct.
    slopes[-80:] = drift * (2.2 if timeframe == "day" else 1.3) + noise[-80:] * 0.3
    closes = np.exp(np.cumsum(slopes))
    closes *= base / closes[-1]
    result = []
    for i, (ts, session) in enumerate(clocks):
        closing = float(closes[i])
        opening = float(closes[i - 1] if i else closes[i] * 0.999)
        width = closing * rng.uniform(0.001, 0.004)
        volume = int(
            rng.integers(80_000, 650_000) if timeframe != "day" else rng.integers(8_000_000, 45_000_000)
        )
        if i >= count - 3:
            volume *= 3
        result.append(
            {
                "timestamp": ts.astimezone(pd.Timestamp.now(tz="UTC").tz).isoformat(),
                "session": session,
                "open": opening,
                "close": closing,
                "high": max(opening, closing) + width,
                "low": min(opening, closing) - width,
                "volume": volume,
                "turnover": float(volume * closing),
                "confirmed": True,
            }
        )
    return result
