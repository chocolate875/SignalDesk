from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache

import exchange_calendars as xcals
import pandas as pd

from .markets import CN, US, Market

NY = US.timezone
SH = CN.timezone


@lru_cache(maxsize=None)
def calendar(market: Market = US):
    # Mainland holidays are precomputed only through the last published year.
    return xcals.get_calendar(
        market.calendar_name, start="2020-01-01", end=None if market == CN else "2035-12-31"
    )


def regular_intervals(cal, day):
    opening, closing = cal.session_open_close(day)
    pause, resume = cal.session_break_start_end(day)
    if pd.isna(pause):
        return [(opening, closing)]
    return [(opening, pause), (resume, closing)]


def session_for(now: datetime, market: Market = US) -> dict:
    if now.tzinfo is None:
        raise ValueError("必须提供带时区时间")
    local = now.astimezone(market.timezone)
    day = pd.Timestamp(local.date())
    cal = calendar(market)
    minutes = local.hour * 60 + local.minute
    trade_day = day + pd.Timedelta(days=1) if market == US and minutes >= 1200 else day
    result = {
        "session": "closed",
        "label": "休市",
        "trading_date": str(trade_day.date()),
        "new_york": now.astimezone(NY).isoformat(),
        "beijing": now.astimezone(SH).isoformat(),
        "early_close": False,
        "calendar": market.calendar_name,
        "code": market.code,
        "name": market.name,
        "timezone": market.timezone.key,
    }
    if trade_day < cal.first_session or trade_day > cal.last_session:
        return {**result, "session": "unknown", "label": "日历待更新"}
    if market != US:
        if day not in cal.sessions:
            return result
        intervals = regular_intervals(cal, day)
        opening, closing = intervals[0][0], intervals[-1][1]
        result.update(
            regular_open=opening.isoformat(),
            regular_close=closing.isoformat(),
            early_close=closing.astimezone(market.timezone).hour < market.close_hour,
        )
        if any(start <= now < end for start, end in intervals):
            result.update(session="regular", label="盘中")
        elif opening < now < closing:
            result.update(session="break", label="午休", break_start=intervals[0][1].isoformat())
        elif closing <= now < closing + market.closing_auction:
            result.update(session="closing_auction", label="收市竞价")
        return result
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


def bar_end(timestamp: datetime, timeframe: str, market: Market = US) -> datetime:
    if timeframe == "day":
        day = pd.Timestamp(timestamp.astimezone(market.timezone).date())
        cal = calendar(market)
        if day in cal.sessions:
            return cal.session_close(day).to_pydatetime() + market.closing_auction
        # An unknown session has no confirmed daily close within the supported calendar.
        return datetime.max.replace(tzinfo=timezone.utc)
    return timestamp + timedelta(minutes=15)


def latest_expected_end(now: datetime, timeframe: str, session: str, market: Market = US) -> datetime | None:
    """Latest completed bar for this session, including closures and half days."""
    cal = calendar(market)
    today = pd.Timestamp(now.astimezone(market.timezone).date())
    if today < cal.first_session or today > cal.last_session or (market != US and session != "regular"):
        return None
    end_ix = cal.sessions.searchsorted(today, side="right")
    for day in reversed(cal.sessions[max(0, end_ix - 2) : end_ix]):
        regular_open = cal.session_open(day).to_pydatetime()
        regular_close = cal.session_close(day).to_pydatetime()
        if timeframe == "day":
            confirmation = regular_close + market.closing_auction
            if confirmation <= now:
                return confirmation
            continue
        if market != US:
            for start, finish in reversed(regular_intervals(cal, day)):
                completed = int((min(now, finish) - start).total_seconds() // 900)
                if completed >= 1:
                    return (start + timedelta(minutes=15 * completed)).to_pydatetime()
            continue
        local_start = datetime.combine(day.date(), datetime.min.time(), NY)
        bounds = {
            "regular": (regular_open, regular_close),
            "pre": (local_start + timedelta(hours=4), regular_open),
            "post": (
                regular_close,
                local_start + timedelta(hours=17 if regular_close.astimezone(NY).hour < 16 else 20),
            ),
            "overnight": (local_start - timedelta(hours=4), local_start + timedelta(hours=4)),
        }
        start, end = bounds[session]
        available = min(now, end)
        completed = int((available - start).total_seconds() // 900)
        if completed >= 1:
            return start + timedelta(minutes=15 * completed)
    return None
