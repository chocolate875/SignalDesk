from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from signaldesk import operators as op
from signaldesk.calendar import NY, calendar, session_for
from signaldesk.indicators import enrich, summarize
from signaldesk.models import RuleSettings


@pytest.fixture
def daily_bars():
    dates = calendar().sessions_in_range("2025-01-02", "2026-12-31")[:340]
    rng = np.random.default_rng(42)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, len(dates))))
    return [
        {
            "timestamp": datetime.combine(day.date(), datetime.min.time(), NY)
            .replace(hour=9, minute=30)
            .isoformat(),
            "session": "regular",
            "open": float(price - 0.3),
            "high": float(price + 1),
            "low": float(price - 1),
            "close": float(price),
            "volume": int(1000 + (i % 17) * 100),
            "turnover": float(price * (1000 + (i % 17) * 100)),
            "confirmed": True,
        }
        for i, (day, price) in enumerate(zip(dates, closes))
    ]


def test_operators_independent_values():
    values = pd.Series([1.0, 3.0, 2.0, 4.0])
    assert op.delay(values, 1).iloc[-1] == 2
    assert op.delta(values, 2).iloc[-1] == 1
    assert op.returns(values, 1).iloc[-1] == 1
    assert op.mean(values, 3).iloc[-1] == 3
    assert op.std(values, 3).iloc[-1] == pytest.approx(np.std([3, 2, 4]))
    assert op.ts_rank(values, 3).iloc[2] == pytest.approx(2 / 3)
    assert op.corr(values, values * 2, 3).iloc[-1] == pytest.approx(1)
    assert op.zscore(pd.Series([2.0] * 8), 3).isna().all()
    with pytest.raises(ValueError):
        op.delay(values, -1)
    with pytest.raises(ValueError):
        op.mean(values, 0)
    with pytest.raises(ValueError):
        op.evaluate("__import__", values)
    assert op.REGISTRY["delta"].metadata(3)["warmup_length"] == 4
    assert op.REGISTRY["corr"].metadata(3)["inputs"] == ["x", "other"]
    assert op.REGISTRY["clip"].metadata()["warmup_length"] == 1


def test_reference_sma_ema_bollinger_and_score(daily_bars):
    now = datetime(2028, 1, 1, tzinfo=timezone.utc)
    rules = RuleSettings()
    frame = enrich(daily_bars, "day", now, rules)
    closes = np.array([b["close"] for b in daily_bars])
    last = frame.iloc[-1]
    assert last.ma20 == pytest.approx(closes[-20:].mean())
    expected_ema = closes[0]
    for price in closes[1:]:
        expected_ema = price * (2 / 21) + expected_ema * (19 / 21)
    assert last.ema20 == pytest.approx(expected_ema)
    assert last.bb_upper == pytest.approx(closes[-20:].mean() + 2 * closes[-20:].std(ddof=0))

    def ema(values, alpha):
        current = values[0]
        result = [current]
        for value in values[1:]:
            current = alpha * value + (1 - alpha) * current
            result.append(current)
        return np.array(result)

    macd = ema(closes, 2 / 13) - ema(closes, 2 / 27)
    signal = ema(macd[25:], 2 / 10)
    assert last.macd == pytest.approx(macd[-1])
    assert last.macd_signal == pytest.approx(signal[-1])
    assert last.macd_hist == pytest.approx(macd[-1] - signal[-1])
    changes = np.diff(closes, prepend=closes[0])
    gain = ema(np.maximum(changes, 0), 1 / 14)[-1]
    loss = ema(np.maximum(-changes, 0), 1 / 14)[-1]
    assert last.rsi == pytest.approx(100 - 100 / (1 + gain / loss))
    ranges = np.maximum.reduce(
        [
            np.full(len(closes), 2),
            np.abs(closes + 1 - np.roll(closes, 1)),
            np.abs(closes - 1 - np.roll(closes, 1)),
        ]
    )
    ranges[0] = 2
    atr = ranges[:14].mean()
    for value in ranges[14:]:
        atr = (13 * atr + value) / 14
    assert last.atr == pytest.approx(atr)
    volumes = np.array([b["volume"] for b in daily_bars])
    assert last.rvol == pytest.approx(volumes[-1] / volumes[-21:-1].mean())
    assert 0.0 <= last.trend <= 100.0
    assert 0.0 <= last.momentum <= 100.0
    assert 0.0 <= last.volume_score <= 100.0
    assert last.score == pytest.approx(0.45 * last.trend + 0.40 * last.momentum + 0.15 * last.volume_score)
    assert frame.iloc[:199].score.isna().all()
    assert frame.iloc[:13].atr.isna().all()


def test_no_future_leakage_and_unconfirmed_bar(daily_bars):
    now = datetime(2028, 1, 1, tzinfo=timezone.utc)
    full = enrich(daily_bars, "day", now, RuleSettings())
    prefix = enrich(daily_bars[:260], "day", now, RuleSettings())
    columns = ["score", "ema20", "rsi", "rvol", "trend", "momentum", "volume_score"]
    pd.testing.assert_frame_equal(full.loc[:259, columns], prefix[columns])
    changed = [dict(b) for b in daily_bars]
    changed[-1]["confirmed"] = False
    result = enrich(changed, "day", now, RuleSettings())
    assert len(result) == len(daily_bars) - 1


def test_bad_bar_restarts_warmup_and_staleness(daily_bars):
    now = datetime(2028, 1, 1, tzinfo=timezone.utc)
    bad = [dict(b) for b in daily_bars]
    bad[-20]["close"] = float("nan")
    frame = enrich(bad, "day", now, RuleSettings())
    assert pd.isna(frame.iloc[-1].score)
    valid = enrich(daily_bars, "day", now, RuleSettings())
    summary = summarize(valid, "day", "regular", now, RuleSettings())
    assert not summary["valid"]
    assert any("过期" in risk for risk in summary["risks"])


def test_calendar_dst_holiday_and_early_close():
    summer = session_for(datetime(2026, 7, 6, 13, 35, tzinfo=timezone.utc))
    winter = session_for(datetime(2026, 1, 5, 14, 35, tzinfo=timezone.utc))
    assert summer["session"] == winter["session"] == "regular"
    assert session_for(datetime(2026, 12, 25, 15, 0, tzinfo=timezone.utc))["session"] == "closed"
    early = session_for(datetime(2026, 11, 27, 18, 30, tzinfo=timezone.utc))
    assert early["early_close"] and early["session"] == "post"
    # Sunday evening belongs to Monday's overnight trading day.
    night = session_for(datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc))
    assert night["session"] == "overnight" and night["trading_date"] == "2026-10-26"
