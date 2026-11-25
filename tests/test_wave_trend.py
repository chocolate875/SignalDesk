from datetime import datetime, timezone

import numpy as np

from signaldesk.calendar import NY, calendar
from signaldesk.demo import DEMO_NAMES, make_bars
from signaldesk.indicators import enrich, summarize
from signaldesk.models import RuleSettings
from signaldesk.wave_trend import compute_wave_trend


def _bars_from_closes(closes: list[float], start_date: str = "2025-06-02") -> list[dict]:
    dates = calendar().sessions_in_range(start_date, "2027-06-30")[: len(closes)]
    out = []
    for i, (day, c) in enumerate(zip(dates, closes)):
        o = closes[i - 1] if i > 0 else c * 0.998
        hi = max(o, c) * 1.008
        lo = min(o, c) * 0.992
        out.append(
            {
                "timestamp": datetime.combine(day.date(), datetime.min.time(), NY)
                .replace(hour=9, minute=30)
                .isoformat(),
                "session": "regular",
                "open": float(o),
                "high": float(hi),
                "low": float(lo),
                "close": float(c),
                "volume": 10_000_000,
                "turnover": float(c * 10_000_000),
                "confirmed": True,
            }
        )
    return out


def _interpolate_path(waypoints: list[tuple[int, float]]) -> list[float]:
    closes: list[float] = []
    for idx in range(len(waypoints) - 1):
        steps, start_p = waypoints[idx]
        next_steps, end_p = waypoints[idx + 1]
        count = next_steps - steps
        seg = np.linspace(start_p, end_p, count, endpoint=(idx == len(waypoints) - 2))
        closes.extend(float(v) for v in seg)
    return closes


def test_wave_trend_all_demo_stocks_and_channel_ordering():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    for symbol, _, _, _, _, _ in DEMO_NAMES:
        bars = make_bars(symbol, "day", now)
        frame = enrich(bars, "day", now, rules)
        summary = summarize(frame, "day", "regular", now, rules, demo=True)
        wt = compute_wave_trend(frame, summary)
        assert wt["available"] is True
        assert wt["trend"]["direction"] in {"uptrend", "downtrend", "sideways"}
        ch = wt["trend"]["channel"]
        assert ch["available"] is True
        assert ch["window"] == 126
        assert ch["start_lower"] < ch["start_mid"] < ch["start_upper"]
        assert ch["end_lower"] < ch["end_mid"] < ch["end_upper"]
        assert wt["summary"] and wt["action_guide"]
        assert wt["wave"]["span_days"] is None or wt["wave"]["span_days"] >= 0


def test_wave_trend_strict_causal_no_future_leakage():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    bars = make_bars("NVDA.US", "day", now)
    cutoff = 360

    frame_full = enrich(bars, "day", now, rules)
    prefix_from_full = frame_full.iloc[:cutoff].copy()
    summary_full = summarize(prefix_from_full, "day", "regular", now, rules, demo=True)
    wt_from_full = compute_wave_trend(prefix_from_full, summary_full)

    # Aggressively mutate future bars and recompute prefix independently.
    prefix_bars = [dict(b) for b in bars[:cutoff]]
    frame_prefix = enrich(prefix_bars, "day", now, rules)
    summary_prefix = summarize(frame_prefix, "day", "regular", now, rules, demo=True)
    wt_prefix = compute_wave_trend(frame_prefix, summary_prefix)

    assert wt_from_full == wt_prefix


def test_wave_trend_recognizes_five_wave_impulse_up_and_obeys_rules():
    # Construct a textbook 5-wave rising impulse (0 -> 1 -> 2 -> 3 -> 4 -> 5).
    # P0=100 -> P1=120 (+20) -> P2=110 (above P0) -> P3=150 (+40) -> P4=134 (above P1=120) -> P5=165 (+31)
    closes = _interpolate_path(
        [
            (0, 108.0),
            (18, 100.0),  # 0
            (36, 120.0),  # 1
            (52, 110.0),  # 2 (> P0=100)
            (76, 150.0),  # 3 (> P1=120, longest)
            (92, 134.0),  # 4 (> P1=120, non-overlapping)
            (112, 165.0),  # 5 (> P3=150)
        ]
    )
    bars = _bars_from_closes(closes)
    now = datetime(2027, 6, 30, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    frame = enrich(bars, "day", now, rules)
    summary = summarize(frame, "day", "regular", now, rules, demo=True)
    wt = compute_wave_trend(frame, summary)

    assert wt["available"] is True
    assert wt["trend"]["direction"] == "uptrend"
    assert wt["wave"]["pattern"] == "impulse_up"
    assert wt["wave"]["span_days"] is not None and wt["wave"]["span_days"] > 60
    assert wt["wave"]["degree_label"]
    labels = [p["wave_label"] for p in wt["wave"]["pivots"] if p["wave_label"]]
    assert labels == ["0", "1", "2", "3", "4", "5"]
    assert len(wt["wave"]["rules_passed"]) == 3


def test_wave_trend_recognizes_abc_correction_in_uptrend():
    # Strong rise establishing uptrend, followed by clean A -> B -> C pullback.
    closes = _interpolate_path(
        [
            (0, 80.0),
            (40, 120.0),
            (58, 160.0),  # 0 (H)
            (72, 140.0),  # A (L)
            (84, 152.0),  # B (H < 160)
            (98, 132.0),  # C (L < 140)
        ]
    )
    bars = _bars_from_closes(closes)
    now = datetime(2027, 6, 30, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    frame = enrich(bars, "day", now, rules)
    summary = summarize(frame, "day", "regular", now, rules, demo=True)
    wt = compute_wave_trend(frame, summary)

    assert wt["available"] is True
    labels = [p["wave_label"] for p in wt["wave"]["pivots"] if p["wave_label"]]
    assert wt["wave"]["pattern"] in {"correction_abc", "impulse_down"}
    assert len(labels) >= 4
    assert wt["wave"]["fib_targets"]


def test_wave_trend_honest_unavailable_on_short_or_broken_history():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    bars = make_bars("AAPL.US", "day", now)
    rules = RuleSettings()
    frame = enrich(bars, "day", now, rules)
    summary = summarize(frame, "day", "regular", now, rules, demo=True)

    assert compute_wave_trend(None, summary)["available"] is False
    assert compute_wave_trend(frame.tail(40), summary)["available"] is False

    broken = frame.copy()
    broken.loc[broken.index[-20], "close"] = float("nan")
    assert compute_wave_trend(broken, summary)["available"] is False
