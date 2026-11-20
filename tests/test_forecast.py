from datetime import datetime, timezone

import numpy as np

from signaldesk.demo import DEMO_NAMES, DEMO_PLANS, make_bars, yield_curve
from signaldesk.forecast import TIER_ORDER, compute_forecast
from signaldesk.indicators import enrich, summarize
from signaldesk.models import RuleSettings
from signaldesk.research import research_context


def _sample_valuation(symbol: str, now: datetime, pe_ttm: float = 28.0) -> dict:
    return {
        "symbol": symbol,
        "pe_ttm": pe_ttm,
        "pb": 5.2,
        "dividend_yield_pct": 1.2,
        "market_cap": 1_000_000_000.0,
        "fetched_at": now.isoformat(),
    }


def _build_context(bars: list[dict], symbol: str = "NVDA.US", pe_ttm: float = 28.0, stop: float | None = None):
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    frame = enrich(bars, "day", now, rules)
    summary = summarize(frame, "day", "regular", now, rules, demo=True)
    last_close = datetime.fromisoformat(bars[-1]["timestamp"])
    research = research_context(_sample_valuation(symbol, now, pe_ttm=pe_ttm), yield_curve(last_close), now, demo=True)
    close = float(frame.iloc[-1]["close"])
    long_plan = {"close": close, "stop": stop, "target": None}
    return now, frame, summary, research, long_plan


def test_forecast_monotonic_and_all_demo_scenarios():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    for symbol, _, _, _, _, _ in DEMO_NAMES:
        bars = make_bars(symbol, "day", now)
        frame = enrich(bars, "day", now, rules)
        summary = summarize(frame, "day", "regular", now, rules, demo=True)
        last_ts = datetime.fromisoformat(bars[-1]["timestamp"])
        research = research_context(_sample_valuation(symbol, now, pe_ttm=26.0), yield_curve(last_ts), now, demo=True)
        close = float(frame.iloc[-1]["close"])
        plan = DEMO_PLANS.get(symbol, {})
        forecast = compute_forecast(frame, summary, research, {"close": close, "stop": plan.get("stop"), "target": plan.get("target")})

        levels = forecast["levels"]
        rating = forecast["rating"]
        assert levels["available"] is True
        assert rating["available"] is True
        assert (
            0
            < levels["stop_loss"]
            < levels["buy_low"]
            < levels["buy_high"]
            <= close
            < levels["sell_low"]
            < levels["sell_high"]
        ), f"Monotonic check failed for {symbol}: {levels} close={close}"
        assert levels["buy_low"] <= levels["ideal_buy"] <= levels["buy_high"]
        assert levels["risk_reward_ratio"] > 0
        assert levels["entry_risk_reward_ratio"] > 0
        assert 1 <= rating["stars"] <= 5
        assert rating["code"] in TIER_ORDER
        assert abs(sum(f["weight"] for f in rating["factors"]) - 1.0) <= 0.01


def test_forecast_causal_no_future_leakage():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    bars = make_bars("NVDA.US", "day", now)
    cutoff = 360

    frame_full = enrich(bars, "day", now, rules)
    prefix_frame_from_full = frame_full.iloc[:cutoff].copy()
    last_prefix_ts = datetime.fromisoformat(bars[cutoff - 1]["timestamp"])
    research_prefix = research_context(_sample_valuation("NVDA.US", now), yield_curve(last_prefix_ts), now, demo=True)
    summary_from_full = summarize(prefix_frame_from_full, "day", "regular", now, rules, demo=True)
    close_cutoff = float(prefix_frame_from_full.iloc[-1]["close"])
    fc_from_full = compute_forecast(prefix_frame_from_full, summary_from_full, research_prefix, {"close": close_cutoff})

    # Alter future bars aggressively and verify prefix forecast is bit-for-bit identical.
    mutated = [dict(b) for b in bars[:cutoff]]
    future_extra = [dict(b, close=b["close"] * 3.0, high=b["high"] * 3.0, low=b["low"] * 3.0) for b in bars[cutoff:]]
    assert len(future_extra) > 0
    frame_prefix = enrich(mutated, "day", now, rules)
    summary_prefix = summarize(frame_prefix, "day", "regular", now, rules, demo=True)
    fc_prefix = compute_forecast(frame_prefix, summary_prefix, research_prefix, {"close": close_cutoff})

    assert fc_from_full == fc_prefix


def test_forecast_low_price_tiny_price_and_high_volatility_downtrend():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    base_bars = make_bars("TSLA.US", "day", now)

    # Low price (~$0.50) must still keep strict monotonic separation and positive stop.
    scale_50c = 0.50 / base_bars[-1]["close"]
    low_price_bars = [
        {
            **b,
            "open": b["open"] * scale_50c,
            "high": b["high"] * scale_50c,
            "low": b["low"] * scale_50c,
            "close": b["close"] * scale_50c,
        }
        for b in base_bars
    ]
    _, frame_lp, summary_lp, research_lp, plan_lp = _build_context(low_price_bars, "LOWP.US")
    fc_lp = compute_forecast(frame_lp, summary_lp, research_lp, plan_lp)
    lv = fc_lp["levels"]
    assert lv["available"] is True
    assert 0 < lv["stop_loss"] < lv["buy_low"] < lv["buy_high"] <= plan_lp["close"] < lv["sell_low"] < lv["sell_high"]

    # Sub-$0.05 tick edge must honestly report unavailable rather than collapsing levels.
    scale_micro = 0.03 / base_bars[-1]["close"]
    micro_bars = [
        {
            **b,
            "open": b["open"] * scale_micro,
            "high": b["high"] * scale_micro,
            "low": b["low"] * scale_micro,
            "close": b["close"] * scale_micro,
        }
        for b in base_bars
    ]
    _, frame_micro, summary_micro, research_micro, plan_micro = _build_context(micro_bars, "TINY.US")
    fc_micro = compute_forecast(frame_micro, summary_micro, research_micro, plan_micro)
    assert fc_micro["levels"]["available"] is False
    assert fc_micro["rating"]["code"] == "unavailable"

    # High-volatility downtrend scenario.
    rng = np.random.default_rng(999)
    hv_bars = []
    px = 200.0
    for b in base_bars:
        px = max(5.0, px * float(np.exp(-0.004 + rng.normal(0, 0.035))))
        hv_bars.append({**b, "open": px * 1.01, "high": px * 1.045, "low": px * 0.955, "close": px})
    _, frame_hv, summary_hv, research_hv, plan_hv = _build_context(hv_bars, "VOL.US")
    fc_hv = compute_forecast(frame_hv, summary_hv, research_hv, plan_hv)
    hv_lv = fc_hv["levels"]
    assert hv_lv["available"] is True
    assert 0 < hv_lv["stop_loss"] < hv_lv["buy_low"] < hv_lv["buy_high"] <= plan_hv["close"] < hv_lv["sell_low"] < hv_lv["sell_high"]


def test_forecast_honest_unavailable_fallback():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    bars = make_bars("NVDA.US", "day", now)
    _, frame, summary, research, plan = _build_context(bars)

    assert compute_forecast(None, summary, research, plan)["rating"]["code"] == "unavailable"
    assert compute_forecast(frame.tail(45), summary, research, plan)["levels"]["available"] is False
    assert compute_forecast(frame, {**summary, "valid": False}, research, plan)["rating"]["available"] is False

    # Recent NaN bar breaking contiguous tail leaves < 60 contiguous valid bars.
    broken = frame.copy()
    broken.loc[broken.index[-25], "close"] = float("nan")
    assert compute_forecast(broken, summary, research, plan)["levels"]["available"] is False


def test_forecast_rating_guardrails_and_missing_valuation():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    bars = make_bars("NVDA.US", "day", now)
    _, frame, summary, research, plan = _build_context(bars, "NVDA.US", pe_ttm=22.0)

    # Force high score baseline to verify guardrails actually cap rating tiers.
    bullish_summary = {**summary, "score": 92.0, "state": "strong", "dimensions": {**summary["dimensions"], "trend": 85.0}}

    # 1) Breached personal stop caps tier <= reduce.
    fc_stop = compute_forecast(frame, bullish_summary, research, {**plan, "stop": plan["close"] + 5.0})
    assert fc_stop["rating"]["code"] in ("reduce", "sell")
    assert any("失效价" in g for g in fc_stop["rating"]["guardrails"])

    # 2) Fresh negative PE caps tier <= hold.
    neg_research = research_context(_sample_valuation("NVDA.US", now, pe_ttm=-15.0), research["curve"], now, demo=True)
    fc_neg = compute_forecast(frame, bullish_summary, neg_research, plan)
    assert TIER_ORDER.index(fc_neg["rating"]["code"]) <= TIER_ORDER.index("hold")
    assert any("市盈率为负" in g for g in fc_neg["rating"]["guardrails"])

    # 3) Weak trend (< 25) caps tier <= hold.
    weak_summary = {
        **bullish_summary,
        "state": "weak",
        "dimensions": {**bullish_summary["dimensions"], "trend": 15.0},
    }
    fc_weak = compute_forecast(frame, weak_summary, research, plan)
    assert TIER_ORDER.index(fc_weak["rating"]["code"]) <= TIER_ORDER.index("hold")
    assert any("空头弱势" in g for g in fc_weak["rating"]["guardrails"])

    # 4) Missing/expired valuation normalizes remaining factor weights cleanly to 1.0.
    stale_research = research_context({}, {}, now, demo=True)
    fc_no_val = compute_forecast(frame, bullish_summary, stale_research, plan)
    val_factor = next(f for f in fc_no_val["rating"]["factors"] if f["key"] == "valuation")
    assert val_factor["score"] is None and val_factor["weight"] == 0.0
    assert abs(sum(f["weight"] for f in fc_no_val["rating"]["factors"]) - 1.0) <= 0.01
