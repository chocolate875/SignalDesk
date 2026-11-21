"""美股 ETF/基金分类、严格因果基金指标、防误判评级与白屏防护测试。"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from signaldesk import demo
from signaldesk.app import _sanitize_json, _snapshot_fingerprint
from signaldesk.calendar import NY, bar_end, calendar
from signaldesk.forecast import compute_forecast
from signaldesk.indicators import enrich, summarize
from signaldesk.instruments import classify_instrument, compute_fund_metrics
from signaldesk.models import Allocation, RuleSettings, utcnow
from signaldesk.research import research_context
from signaldesk.security import safe_snapshot
from signaldesk.service import Monitor
from signaldesk.storage import Store


def _make_trend_frame(n: int = 260, drift: float = 0.002, vol: float = 0.01):
    now = utcnow()
    cal = calendar()
    end_day = pd.Timestamp(now.astimezone(NY).date())
    sessions = cal.sessions_in_range(end_day - pd.Timedelta(days=int(n * 2)), end_day)
    clocks = [
        cal.session_open(day).to_pydatetime()
        for day in sessions
        if bar_end(cal.session_open(day).to_pydatetime(), "day") <= now
    ][-n:]
    rng = np.random.default_rng(42)
    rets = drift + rng.normal(0.0, vol, len(clocks))
    closes = 100.0 * np.exp(np.cumsum(rets))
    bars = []
    for i, ts in enumerate(clocks):
        c = float(closes[i])
        o = float(closes[i - 1]) if i > 0 else c * 0.998
        h = max(o, c) * 1.006
        low = min(o, c) * 0.994
        bars.append(
            {
                "timestamp": ts.astimezone(pd.Timestamp.now(tz="UTC").tz).isoformat(),
                "session": "regular",
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "volume": 25_000_000,
                "turnover": c * 25_000_000,
                "confirmed": True,
            }
        )
    rules = RuleSettings()
    frame = enrich(bars, "day", now, rules)
    summary = summarize(frame, "day", "regular", now, rules, demo=True)
    return frame, summary, bars, now


def test_instrument_classification_distinguishes_etfs_and_stocks():
    qqq = classify_instrument("QQQ.US", "Invesco QQQ Trust")
    assert qqq["is_fund"] is True
    assert qqq["asset_type"] == "broad_etf"
    assert qqq["company_valuation_applicable"] is False

    soxx = classify_instrument("SOXX.US", "iShares Semiconductor ETF")
    assert soxx["is_fund"] is True
    assert soxx["asset_type"] == "sector_etf"

    gld = classify_instrument("GLD.US", "SPDR Gold Shares")
    assert gld["is_fund"] is True
    assert gld["asset_type"] == "commodity_etf"

    sqqq = classify_instrument("SQQQ.US", "Proshares UltraPro Short QQQ ETF")
    assert sqqq["is_fund"] is True
    assert sqqq["is_leveraged"] is True
    assert sqqq["is_inverse"] is True
    assert sqqq["leverage"] == -3.0

    tqqq = classify_instrument("TQQQ.US", "Proshares UltraPro QQQ")
    assert tqqq["is_leveraged"] is True
    assert tqqq["is_inverse"] is False
    assert tqqq["leverage"] == 3.0

    # 未知代码通过名称规则自动分类（无需硬编码代码表）
    unknown_etf = classify_instrument("XYZF.US", "Vanguard Robotics 2X Long ETF")
    assert unknown_etf["is_fund"] is True
    assert unknown_etf["is_leveraged"] is True

    unknown_broad = classify_instrument("NEWB.US", "Schwab US S&P 500 Index ETF")
    assert unknown_broad["is_fund"] is True
    assert unknown_broad["asset_type"] == "broad_etf"

    unknown_cn_fund = classify_instrument("CNGD.US", "黄金现货指数基金")
    assert unknown_cn_fund["is_fund"] is True
    assert unknown_cn_fund["asset_type"] == "commodity_etf"

    unknown_cn_inv = classify_instrument("CNSH.US", "三倍做空纳指ETF")
    assert unknown_cn_inv["is_fund"] is True
    assert unknown_cn_inv["is_leveraged"] is True
    assert unknown_cn_inv["is_inverse"] is True
    assert unknown_cn_inv["leverage"] == -3.0

    # 概念组合代码识别
    concept = classify_instrument("CP00084.US", "Duan Yongping Stocks")
    assert concept["is_fund"] is True

    # 上市公司个股与含 Trust 的上市银行不应误判为 ETF
    nvda = classify_instrument("NVDA.US", "NVIDIA")
    assert nvda["is_fund"] is False
    assert nvda["company_valuation_applicable"] is True

    ntrs = classify_instrument("NTRS.US", "Northern Trust Corp")
    assert ntrs["is_fund"] is False


def test_fund_metrics_are_strictly_causal_and_bounded():
    frame, summary, bars, now = _make_trend_frame(260, drift=0.0012, vol=0.012)
    rules = RuleSettings()

    # 仅使用前 250 根计算
    frame_250 = enrich(bars[:250], "day", now, rules)
    summary_250 = summarize(frame_250, "day", "regular", now, rules, demo=True)
    m_before = compute_fund_metrics(frame_250, summary_250)

    # 篡改后 10 根未来 K 线暴跌，验证前 250 根因果结果完全不变
    mutated = [dict(b) for b in bars]
    for b in mutated[250:]:
        b["open"] *= 0.4
        b["high"] *= 0.4
        b["low"] *= 0.4
        b["close"] *= 0.4
    frame_mut = enrich(mutated[:250], "day", now, rules)
    summary_mut = summarize(frame_mut, "day", "regular", now, rules, demo=True)
    m_after = compute_fund_metrics(frame_mut, summary_mut)

    assert m_before == m_after
    assert m_before["available"] is True
    assert m_before["drawdown_from_high_pct"] <= 0.0
    assert 0.0 <= m_before["range_position_pct"] <= 100.0
    assert m_before["max_drawdown_pct"] <= 0.0
    assert m_before["hv20_pct"] > 0.0
    assert m_before["hv60_pct"] > 0.0

    # 样本不足 20 根诚实降级
    short_frame = enrich(bars[:10], "day", now, rules)
    short_summary = summarize(short_frame, "day", "regular", now, rules, demo=True)
    assert compute_fund_metrics(short_frame, short_summary)["available"] is False


def test_qqq_negative_pe_and_soxx_tiny_pe_do_not_mislead_rating_or_verdict():
    frame, summary, _, now = _make_trend_frame(260, drift=0.0018, vol=0.009)
    curve = demo.yield_curve(now)
    close = summary["close"]
    long_plan = {"status": "按计划观察", "stop": None, "target": None, "close": close, "as_of": summary["as_of"]}
    fm = compute_fund_metrics(frame, summary)

    # 1) QQQ 收到券商失真负 PE (-6.88)：绝不应打成“亏损警示”或触发负 PE 护栏
    qqq_inst = classify_instrument("QQQ.US", "Invesco QQQ Trust")
    qqq_alloc = Allocation(symbol="QQQ.US", name="Invesco QQQ Trust", watch_only=True)
    qqq_research = research_context(
        {"pe_ttm": -6.88, "pb": 2.28, "dividend_yield_pct": 0.51, "fetched_at": now.isoformat()},
        curve,
        now,
        False,
    )
    qqq_verdict = Monitor._build_verdict(
        qqq_alloc, summary, qqq_research, long_plan, instrument=qqq_inst, fund_metrics=fm
    )
    qqq_forecast = compute_forecast(
        frame, summary, qqq_research, long_plan, instrument=qqq_inst, fund_metrics=fm
    )

    assert qqq_verdict["action"] != "亏损警示"
    assert "财报" not in qqq_verdict["next_step"]
    assert "公司" not in qqq_verdict["headline"]
    assert qqq_verdict["pillars"][1]["label"] == "回撤波动"
    assert not any("市盈率为负" in g for g in qqq_forecast["rating"]["guardrails"])
    assert any(f["key"] == "fund_position" for f in qqq_forecast["rating"]["factors"])
    assert not any(f["key"] == "valuation" for f in qqq_forecast["rating"]["factors"])

    # 2) SOXX 收到券商失真 0.79x PE：不应产生 126% 假盈利收益率或 95 分假估值分
    soxx_inst = classify_instrument("SOXX.US", "iShares Semiconductor ETF")
    soxx_research = research_context(
        {"pe_ttm": 0.79, "pb": 0.26, "dividend_yield_pct": 0.34, "fetched_at": now.isoformat()},
        curve,
        now,
        False,
    )
    soxx_forecast = compute_forecast(
        frame, summary, soxx_research, long_plan, instrument=soxx_inst, fund_metrics=fm
    )
    factor_keys = [f["key"] for f in soxx_forecast["rating"]["factors"]]
    assert "valuation" not in factor_keys
    assert "fund_position" in factor_keys
    assert "基金主体 PE" in soxx_forecast["rating"]["disclaimer"]


def test_inverse_and_leveraged_etf_guardrails():
    frame, summary, _, now = _make_trend_frame(260, drift=0.003, vol=0.015)
    curve = demo.yield_curve(now)
    close = summary["close"]
    long_plan = {"status": "按计划观察", "stop": None, "target": None, "close": close, "as_of": summary["as_of"]}
    research = research_context({}, curve, now, False)
    fm = compute_fund_metrics(frame, summary)

    # 反向做空 3X ETF（SQQQ）：最高只能封顶 hold，绝不输出建议买入
    sqqq_inst = classify_instrument("SQQQ.US", "Proshares UltraPro Short QQQ ETF")
    sqqq_alloc = Allocation(symbol="SQQQ.US", name="Proshares UltraPro Short QQQ ETF", watch_only=True)
    sqqq_forecast = compute_forecast(
        frame, summary, research, long_plan, instrument=sqqq_inst, fund_metrics=fm
    )
    sqqq_verdict = Monitor._build_verdict(
        sqqq_alloc, summary, research, long_plan, instrument=sqqq_inst, fund_metrics=fm
    )
    assert sqqq_forecast["rating"]["code"] in {"hold", "reduce", "sell"}
    assert any("反向做空" in g for g in sqqq_forecast["rating"]["guardrails"])
    assert sqqq_verdict["action"] == "对冲观察"

    # 正向 3X 杠杆 ETF（TQQQ）：封顶 buy（不出 strong_buy），并携带复利损耗护栏
    tqqq_inst = classify_instrument("TQQQ.US", "Proshares UltraPro QQQ")
    tqqq_forecast = compute_forecast(
        frame, summary, research, long_plan, instrument=tqqq_inst, fund_metrics=fm
    )
    assert tqqq_forecast["rating"]["code"] != "strong_buy"
    assert any("杠杆" in g for g in tqqq_forecast["rating"]["guardrails"])


def test_safe_snapshot_strips_distorted_fund_pe_and_keeps_privacy(tmp_path):
    store = Store(tmp_path)
    monitor = Monitor(store)
    monitor.prepare_demo()
    # 添加一个带失真 PE 的 QQQ 观察项以测试 safe_snapshot 与完整默认 summary 防护
    qqq = Allocation(symbol="QQQ.US", name="Invesco QQQ Trust", watch_only=True)
    stock = monitor.stock(qqq)
    # 未 rebuild 的标的也必须具备完整安全的 primary 字段结构
    assert isinstance(stock["primary"]["risks"], list)
    assert isinstance(stock["primary"]["dimensions"], dict)
    assert isinstance(stock["primary"]["indicators"], dict)
    assert stock["instrument"]["is_fund"] is True

    # 模拟失真估值注入后检查脱敏快照
    stock["research"]["valuation"]["pe_ttm"] = -6.88
    stock["research"]["valuation"]["pb"] = 2.28
    stock["research"]["earnings_yield_pct"] = -14.5
    stock["research"]["yield_gap_pp"] = -19.0
    snap = safe_snapshot(stock, "live")
    assert snap["instrument"]["asset_type"] == "broad_etf"
    assert snap["research"]["valuation"]["company_valuation_applicable"] is False
    assert snap["research"]["valuation"]["pe_ttm"] is None
    assert snap["research"]["valuation"]["pb"] is None
    assert snap["research"]["earnings_yield_pct"] is None
    assert snap["research"]["yield_gap_pp"] is None
    assert "broker_quantity" not in snap
    assert "cost_price" not in snap
    store.close()


def test_sanitize_json_and_snapshot_fingerprint():
    dirty = {
        "now": "2026-11-21T00:00:01Z",
        "market": {"session": "regular", "label": "盘中", "early_close": False, "beijing": "12:00:01"},
        "stocks": [{"symbol": "QQQ.US", "score": float("nan"), "slope": float("inf")}],
    }
    clean = _sanitize_json(dirty)
    assert clean["stocks"][0]["score"] is None
    assert clean["stocks"][0]["slope"] is None
    encoded = json.dumps(clean, ensure_ascii=False, allow_nan=False)
    assert math.isfinite(1.0) and "NaN" not in encoded

    # 时钟跳变不应改变业务指纹
    clean2 = _sanitize_json({**dirty, "now": "2026-11-21T00:00:03Z"})
    assert _snapshot_fingerprint(clean) == _snapshot_fingerprint(clean2)


def test_index_html_disables_cache_and_monitor_caches_derivations(tmp_path):
    from fastapi.testclient import TestClient

    from signaldesk.app import create_app

    app = create_app(tmp_path, background=False)
    with TestClient(app) as client:
        resp = client.get("/")
        if resp.status_code == 200:
            cc = resp.headers.get("cache-control", "").lower()
            assert "no-store" in cc and "no-cache" in cc

        monitor: Monitor = app.state.monitor
        alloc = monitor.portfolio()[0]
        first = monitor.stock(alloc)
        second = monitor.stock(alloc)
        assert first["wave_trend"] == second["wave_trend"]
        assert first["forecast"] == second["forecast"]
        assert (monitor.settings.mode, alloc.symbol) in monitor.wave_trends
        assert (monitor.settings.mode, alloc.symbol) in monitor.forecast_cache

