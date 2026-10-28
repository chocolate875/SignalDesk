from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd

NY = ZoneInfo("America/New_York")
SH = ZoneInfo("Asia/Shanghai")


@lru_cache(maxsize=1)
def calendar():
    return xcals.get_calendar("XNYS", start="2020-01-01", end="2035-12-31")


def session_for(now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError("必须提供带时区时间")
    local = now.astimezone(NY)
    day = pd.Timestamp(local.date())
    cal = calendar()
    minutes = local.hour * 60 + local.minute
    trade_day = day + pd.Timedelta(days=1) if minutes >= 1200 else day
    result = {"session": "closed", "label": "休市", "trading_date": str(trade_day.date()),
              "new_york": local.isoformat(), "beijing": now.astimezone(SH).isoformat(),
              "early_close": False, "calendar": "XNYS"}
    if minutes >= 1200 or minutes < 240:
        if cal.is_session(trade_day):
            result.update(session="overnight", label="夜盘")
        return result
    if not cal.is_session(day):
        return result
    open_at = cal.session_open(day).to_pydatetime()
    close_at = cal.session_close(day).to_pydatetime()
    early = close_at.astimezone(NY).hour < 16
    result["early_close"] = early
    if minutes < 570:
        result.update(session="pre", label="盘前")
    elif now.astimezone(timezone.utc) < close_at:
        result.update(session="regular", label="盘中")
    elif minutes < (1020 if early else 1200):
        result.update(session="post", label="盘后")
    result["regular_open"] = open_at.isoformat()
    result["regular_close"] = close_at.isoformat()
    return result


def bar_end(timestamp: datetime, timeframe: str) -> datetime:
    if timeframe == "day":
        local_day = timestamp.astimezone(NY).date()
        cal = calendar()
        if cal.is_session(pd.Timestamp(local_day)):
            return cal.session_close(pd.Timestamp(local_day)).to_pydatetime()
        return timestamp + timedelta(days=1)
    return timestamp + timedelta(minutes=15)


def latest_expected_end(now: datetime, timeframe: str, session: str) -> datetime | None:
    """Latest completed bar for this session, including closures and half days."""
    cal = calendar()
    for offset in range(10):
        day = pd.Timestamp(now.astimezone(NY).date() - timedelta(days=offset))
        if not cal.is_session(day):
            continue
        regular_open = cal.session_open(day).to_pydatetime()
        regular_close = cal.session_close(day).to_pydatetime()
        if timeframe == "day":
            if regular_close <= now:
                return regular_close
            continue
        local_start = datetime.combine(day.date(), datetime.min.time(), NY)
        bounds = {
            "regular": (regular_open, regular_close),
            "pre": (local_start + timedelta(hours=4), regular_open),
            "post": (regular_close, local_start + timedelta(hours=17 if regular_close.astimezone(NY).hour < 16 else 20)),
            "overnight": (local_start - timedelta(hours=4), local_start + timedelta(hours=4)),
        }
        start, end = bounds[session]
        available = min(now, end)
        completed = int((available - start).total_seconds() // 900)
        if completed >= 1:
            return start + timedelta(minutes=15 * completed)
    return None
