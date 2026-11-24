"""针对学术升级指标（残差动量、FIP/ID、日夜拉锯、Yang-Zhang、MAX5、风险预算及因果性）的专项测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from signaldesk.calendar import NY, calendar
from signaldesk.demo import make_bars, make_benchmark_bars, yield_curve
from signaldesk.extended_hours import summarize_extended_hours
from signaldesk.factor_eval import evaluate_factor_panel
from signaldesk.factors import compute_academic_factors, compute_yang_zhang_hv
from signaldesk.forecast import compute_forecast
from signaldesk.indicators import RULE_VERSION, enrich, summarize
from signaldesk.models import RuleSettings
from signaldesk.research import research_context
from signaldesk.security import safe_snapshot


def _build_bars_from_returns(
    simple_rets: list[float],
    *,
    start_price: float = 100.0,
    overnight_splits: list[float] | None = None,
    volume: int = 8_000_000,
    start_date: str = "2024-06-03",
) -> list[dict]:
    """基于确定性收益率与日夜拆分比例生成标准常规美股日线序列。"""
    days = calendar().sessions_in_range(start_date, "2027-12-31")[: len(simple_rets) + 1]
    bars: list[dict] = []
    prev_close = start_price
    for idx, day in enumerate(days):
        ts = calendar().session_open(day).to_pydatetime().isoformat()
        if idx == 0:
            o = prev_close * 0.999
            c = prev_close
        else:
            r = simple_rets[idx - 1]
            c = prev_close * (1.0 + r)
            if overnight_splits is not None:
                o = prev_close * (1.0 + overnight_splits[idx - 1])
            else:
                o = prev_close * (1.0 + r * 0.35)
        hi = max(o, c) * 1.006
        lo = min(o, c) * 0.994
        bars.append(
            {
                "timestamp": ts,
                "session": "regular",
                "open": float(o),
                "high": float(hi),
                "low": float(lo),
                "close": float(c),
                "volume": int(volume),
                "turnover": float(c * volume),
                "confirmed": True,
            }
        )
        prev_close = c
    return bars


def test_academic_factors_and_forecast_no_future_leakage():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    bars = make_bars("NVDA.US", "day", now)
    spy_bars = make_benchmark_bars("SPY.US", now)
    cutoff = 900  # 与最后 340 日基准 SPY 形成 >= 220 日重叠窗口

    full_frame = enrich(bars, "day", now, rules)
    spy_full = enrich(spy_bars, "day", now, rules)
    prefix_slice = full_frame.iloc[:cutoff].copy()
    cutoff_date = bars[cutoff - 1]["timestamp"][:10]

    # 极端篡改 cutoff 之后个股与未来 SPY 的价格（放大 5 倍），验证截断历史时点逐字段一致
    mutated_bars = [dict(b) for b in bars[:cutoff]]
    future_spy = [
        {**b, "open": b["open"] * 5.0, "high": b["high"] * 5.0, "low": b["low"] * 5.0, "close": b["close"] * 5.0}
        if b["timestamp"][:10] > cutoff_date
        else dict(b)
        for b in spy_bars
    ]
    prefix_frame = enrich(mutated_bars, "day", now, rules)
    spy_mutated_future = enrich(future_spy, "day", now, rules)

    val = {"pe_ttm": 25.0, "pb": 6.0, "dividend_yield_pct": 0.4, "turnover_rate_pct": 1.8, "market_cap": 3e12, "fetched_at": now.isoformat()}
    f_from_full = compute_academic_factors(prefix_slice, spy_frame=spy_full, valuation=val)
    f_from_prefix = compute_academic_factors(prefix_frame, spy_frame=spy_mutated_future, valuation=val)
    assert f_from_full == f_from_prefix
    assert f_from_full["available"] is True
    assert f_from_full["residual_mom_z"] is not None
    assert f_from_full["info_discreteness"] is not None

    sum_prefix = summarize(prefix_frame, "day", "regular", now, rules, demo=True)
    res_prefix = research_context(val, yield_curve(datetime.fromisoformat(bars[cutoff - 1]["timestamp"])), now, demo=True)
    plan_prefix = {"close": float(prefix_frame.iloc[-1]["close"]), "stop": None, "target": None}
    fc_1 = compute_forecast(prefix_slice, sum_prefix, res_prefix, plan_prefix, factors=f_from_full, macro={"risk_gauge": {"red_count": 2}})
    fc_2 = compute_forecast(prefix_frame, sum_prefix, res_prefix, plan_prefix, factors=f_from_prefix, macro={"risk_gauge": {"red_count": 2}})
    assert fc_1 == fc_2
    assert RULE_VERSION == "fusion-2.0.0"


def test_residual_momentum_fip_id_and_lottery_guardrail():
    now = datetime(2027, 10, 1, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    # 基准 SPY 带正常日常波动且温和上行
    spy_rets = [0.0024 if i % 2 == 0 else -0.0016 for i in range(280)]
    spy_bars = _build_bars_from_returns(spy_rets)
    spy_frame = enrich(spy_bars, "day", now, rules)

    # 1) 连续慢牛：280 天稳步小阳上涨（0.18%/天），极低离散度 ID < -0.10
    steady_rets = [0.0022 if i % 5 != 0 else -0.0005 for i in range(280)]
    steady_bars = _build_bars_from_returns(steady_rets)
    steady_frame = enrich(steady_bars, "day", now, rules)
    steady_summary = summarize(steady_frame, "day", "regular", now, rules, demo=True)
    f_steady = compute_academic_factors(steady_frame, spy_frame=spy_frame)

    assert f_steady["residual_mom_z"] is not None and f_steady["residual_mom_z"] > 1.0
    assert f_steady["info_discreteness"] is not None and f_steady["info_discreteness"] <= -0.10
    assert f_steady["id_label"] == "连续慢牛"
    assert f_steady["lottery_overheated"] is False

    # 2) 彩票脉冲股：过去阴跌较多但最近 5 天突然暴力脉冲（每天 +11%），同时触发 MAX5 彩票过热与脉冲跳涨
    spike_rets = [-0.0012] * 255 + [-0.002] * 20 + [0.11, 0.10, 0.09, 0.08, 0.12]
    spike_bars = _build_bars_from_returns(spike_rets)
    spike_frame = enrich(spike_bars, "day", now, rules)
    spike_summary = summarize(spike_frame, "day", "regular", now, rules, demo=True)
    f_spike = compute_academic_factors(spike_frame, spy_frame=spy_frame)

    assert f_spike["lottery_overheated"] is True
    assert f_spike["max5_21d_pct"] is not None and f_spike["max5_21d_pct"] >= 6.5

    val = {"pe_ttm": 22.0, "pb": 4.0, "dividend_yield_pct": 1.0, "fetched_at": now.isoformat()}
    curve = yield_curve(datetime.fromisoformat(steady_bars[-1]["timestamp"]))
    res = research_context(val, curve, now, demo=True)

    fc_steady = compute_forecast(
        steady_frame, steady_summary, res, {"close": steady_summary["close"]}, factors=f_steady
    )
    fc_spike = compute_forecast(
        spike_frame, spike_summary, res, {"close": spike_summary["close"]}, factors=f_spike
    )
    assert fc_steady["rating"]["score"] > fc_spike["rating"]["score"]
    assert any("MAX5" in g for g in fc_spike["rating"]["guardrails"])
    assert fc_spike["rating"]["code"] in {"hold", "reduce", "sell"}


def test_overnight_vs_intraday_tug_of_war_and_extended_hours_alert():
    now = datetime(2027, 10, 1, 22, 0, tzinfo=timezone.utc)
    rules = RuleSettings()
    # 构造近 20 天「高开低走」派发序列：每天隔夜跳空 +1.0%，盘中砸跌 -1.1%
    rets = [0.001] * 40 + [-0.0011] * 25
    on_splits = [0.0005] * 40 + [0.010] * 25
    bars = _build_bars_from_returns(rets, overnight_splits=on_splits)
    frame = enrich(bars, "day", now, rules)
    f_tug = compute_academic_factors(frame)

    assert f_tug["overnight_20d_pct"] is not None and f_tug["overnight_20d_pct"] > 10.0
    assert f_tug["intraday_20d_pct"] is not None and f_tug["intraday_20d_pct"] < -10.0
    assert f_tug["tug_of_war_state"] == "night_pump_day_dump"
    assert f_tug["tug_of_war_label"] == "高开低走特征"

    # 当盘前继续大幅高开 +4% 时，盘外引擎应主动发出谨防追高警告，不输出单纯 positive
    quote_ts = now.astimezone(NY) - timedelta(hours=1)
    ext = summarize_extended_hours(
        quote={
            "last": 100.0,
            "timestamp": (quote_ts - timedelta(hours=2)).isoformat(),
            "extended": {
                "pre": {
                    "last": 104.0,
                    "prev_close": 100.0,
                    "turnover": 25_000_000.0,
                    "timestamp": quote_ts.isoformat(),
                }
            },
        },
        market={"session": "pre"},
        long_plan={"close": 100.0},
        wave_trend=None,
        forecast=None,
        now=now,
        factors=f_tug,
    )
    assert ext["tug_of_war"]["state"] == "night_pump_day_dump"
    assert ext["alert_level"] == "warning"
    assert any("高开低走" in item for item in ext["triggers"])


def test_yang_zhang_captures_overnight_gaps_and_risk_budget_scales_exposure():
    # 收盘几乎不变，但每天大幅隔夜跳空 +3% / -3% 且盘中拉回：传统收盘 HV 极低，Yang-Zhang 必须敏锐捕获
    opens = np.array([100.0 if i == 0 else (103.5 if i % 2 == 0 else 96.5) for i in range(65)])
    closes = np.array([100.0 + (i % 2) * 0.1 for i in range(65)])
    highs = np.maximum(opens, closes) * 1.005
    lows = np.minimum(opens, closes) * 0.995
    yz60 = compute_yang_zhang_hv(opens, highs, lows, closes, 60)
    close_hv60 = float(np.std(np.diff(np.log(closes[-61:])), ddof=1) * np.sqrt(252.0) * 100.0)
    assert yz60 is not None and yz60 > 35.0
    assert yz60 > close_hv60 * 5.0

    # 验证风险预算与宏观红灯联动折算
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    bars = make_bars("NVDA.US", "day", now)
    frame = enrich(bars, "day", now, RuleSettings())
    summary = summarize(frame, "day", "regular", now, RuleSettings(), demo=True)
    res = research_context({"pe_ttm": 25.0, "fetched_at": now.isoformat()}, yield_curve(now), now, demo=True)
    factors = compute_academic_factors(frame)

    fc_calm = compute_forecast(frame, summary, res, {"close": summary["close"]}, factors=factors, macro={"risk_gauge": {"red_count": 1}})
    fc_storm = compute_forecast(frame, summary, res, {"close": summary["close"]}, factors=factors, macro={"risk_gauge": {"red_count": 5}})

    rb_calm = fc_calm["risk_budget"]
    rb_storm = fc_storm["risk_budget"]
    assert rb_calm["available"] is True
    assert rb_calm["macro_multiplier"] == 1.0
    assert rb_storm["macro_multiplier"] == 0.70
    assert rb_storm["suggested_exposure_ratio"] <= rb_calm["suggested_exposure_ratio"]
    assert rb_storm["trailing_stop"] < rb_storm["peak_60d"]


def test_factor_eval_and_safe_snapshot_privacy():
    now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
    bars_map = {sym: make_bars(sym, "day", now) for sym, *_ in [("NVDA.US",), ("AAPL.US",), ("MSFT.US",), ("GOOGL.US",), ("AMZN.US",), ("META.US",)]}
    spy_bars = make_benchmark_bars("SPY.US", now)
    report = evaluate_factor_panel(bars_map, spy_bars=spy_bars, step=15)
    assert report["included_symbols_count"] == 6
    assert report["panel_observations"] > 0
    assert "residual_mom_z" in report["factor_ic"]
    assert len(report["top_collinear_pairs"]) > 0
    assert report["trailing_stop_comparison"]["20d"]["samples"] > 0

    # 校验脱敏快照包含新学术指标，但严禁泄露持仓股数、成本与净资产
    fake_stock = {
        "symbol": "NVDA.US",
        "name": "英伟达",
        "broker_quantity": 100.0,
        "long_quantity": 100.0,
        "cost_price": 110.25,
        "weight_percent": 22.5,
        "reconciled": True,
        "sleeves": ["long"],
        "watch_only": False,
        "long_plan": {"status": "例行复核", "close": 165.0, "stop": 130.0, "target": 210.0},
        "academic_factors": {"available": True, "residual_mom_z": 1.24, "info_discreteness": -0.18},
        "forecast": {
            "rating": {"code": "buy", "label": "建议买入", "score": 71.2, "confidence": "高"},
            "levels": {"available": True, "buy_low": 140.0, "buy_high": 152.0, "sell_low": 180.0, "sell_high": 195.0, "stop_loss": 125.0, "risk_reward_ratio": 1.6},
            "risk_budget": {"available": True, "suggested_exposure_ratio": 0.52, "trailing_stop": 154.0},
        },
        "research": {
            "valuation": {"source": "LongPort", "pe_ttm": 25.0, "pb": 10.0, "turnover_rate_pct": 1.85, "market_cap": 3.5e12, "fresh": True},
            "curve": {"ten_year": 4.2, "fresh": True},
        },
        "extended_hours": {"available": True, "tug_of_war": {"available": True, "state": "neutral"}},
    }
    snap = safe_snapshot(fake_stock, "live")
    assert snap["academic_factors"]["residual_mom_z"] == 1.24
    assert snap["forecast"]["risk_budget"]["suggested_exposure_ratio"] == 0.52
    assert snap["research"]["valuation"]["turnover_rate_pct"] == 1.85
    assert snap["extended_hours"]["tug_of_war"]["state"] == "neutral"
    dumped = str(snap)
    assert "broker_quantity" not in dumped
    assert "cost_price" not in dumped
    assert "110.25" not in dumped
    assert "net_assets" not in dumped
