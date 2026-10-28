"""Deterministic synthetic fixtures. No downloaded market prices, no real holdings."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .calendar import NY, bar_end, calendar
from .models import Allocation

DEMO_NAMES = [
    ("NVDA.US", "英伟达", 142.8, 12, 8, 0.0012),
    ("AAPL.US", "苹果", 232.4, 24, 0, 0.0007),
    ("MSFT.US", "微软", 427.6, 12, 0, 0.0004),
    ("GOOGL.US", "谷歌", 178.2, 20, 0, -0.0003),
    ("AMZN.US", "亚马逊", 204.3, 16, 0, 0.0002),
    ("META.US", "Meta", 582.5, 0, 6, -0.0010),
    ("TSLA.US", "特斯拉", 268.7, 0, 10, -0.0014),
    ("AMD.US", "超威半导体", 153.6, 0, 14, 0.0009),
]


def allocations() -> list[Allocation]:
    return [Allocation(symbol=s, name=name, long_quantity=l, short_quantity=q,
                       broker_quantity=l+q, available_quantity=l+q, cost_price=round(price*0.93, 2))
            for s, name, price, l, q, _ in DEMO_NAMES]


def make_bars(symbol: str, timeframe: str, now: datetime) -> list[dict]:
    n = next(i for i, item in enumerate(DEMO_NAMES) if item[0] == symbol) if symbol in {x[0] for x in DEMO_NAMES} else 1
    _, _, base, _, _, drift = DEMO_NAMES[n]
    rng = np.random.default_rng(2000 + n + (0 if timeframe == "day" else 100))
    cal = calendar()
    end_day = pd.Timestamp(now.astimezone(NY).date())
    days = cal.sessions_in_range(end_day - pd.Timedelta(days=620 if timeframe == "day" else 55), end_day)
    clocks = []
    if timeframe == "day":
        for day in days[-320:]:
            ts = cal.session_open(day).to_pydatetime()
            if bar_end(ts, "day") <= now:
                clocks.append((ts, "regular"))
    else:
        for day in days[-32:]:
            midnight = datetime.combine(day.date(), datetime.min.time(), NY)
            close = cal.session_close(day).to_pydatetime()
            bounds = [(midnight-timedelta(hours=4), midnight+timedelta(hours=4), "overnight"),
                      (midnight+timedelta(hours=4), midnight+timedelta(hours=9, minutes=30), "pre"),
                      (cal.session_open(day).to_pydatetime(), close, "regular"),
                      (close, midnight+timedelta(hours=17 if close.astimezone(NY).hour < 16 else 20), "post")]
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
        opening = float(closes[i-1] if i else closes[i] * 0.999)
        width = closing * rng.uniform(0.001, 0.004)
        volume = int(rng.integers(80_000, 650_000) if timeframe != "day" else rng.integers(8_000_000, 45_000_000))
        if i >= count - 3:
            volume *= 3
        result.append({"timestamp": ts.astimezone(pd.Timestamp.now(tz="UTC").tz).isoformat(),
                       "session": session, "open": opening, "close": closing,
                       "high": max(opening, closing) + width, "low": min(opening, closing) - width,
                       "volume": volume, "turnover": float(volume * closing), "confirmed": True})
    return result
