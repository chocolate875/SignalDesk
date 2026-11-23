from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from signaldesk.demo import make_bars
from signaldesk.forecast import _contiguous_regular_tail
from signaldesk.indicators import enrich, summarize
from signaldesk.models import Allocation, RuleSettings
from signaldesk.service import Monitor
from signaldesk.storage import Store
from signaldesk.wave_trend import _causal_swings, compute_wave_trend


def test_contiguous_tail_excludes_nan_break_row_and_recovers_wave_swings():
    """回归 SOXL 等 10 股波浪待确认 bug：历史某根无效 NaN 行不得被包含在连续尾部首行导致全序列拐点归零。"""
    now = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)
    bars = make_bars("NVDA.US", "day", now)[-220:]
    # 为后 150 根叠加清晰的波段起伏（模拟高波杠杆 ETF），确保存在多段明确拐点
    for idx in range(65, len(bars)):
        mult = 1.0 + 0.16 * np.sin((idx - 65) * 0.24)
        bars[idx] = {
            **bars[idx],
            "open": round(bars[idx]["open"] * mult, 2),
            "high": round(bars[idx]["high"] * mult, 2),
            "low": round(bars[idx]["low"] * mult, 2),
            "close": round(bars[idx]["close"] * mult, 2),
        }
    # 人为在历史中段制造一根 OHLC 违法的脏数据（类似 2023-06-05 异常记录），触发 enrich 置为 NaN
    bars[60] = {**bars[60], "high": 1.0, "low": 999.0}

    frame = enrich(bars, "day", now, RuleSettings())
    tail = _contiguous_regular_tail(frame)
    assert len(tail) == len(bars) - 61
    assert tail["close"].notna().all()
    assert tail["high"].notna().all()
    assert tail["low"].notna().all()
    assert np.isfinite(tail["high"].iloc[0])
    assert np.isfinite(tail["low"].iloc[0])

    swings = _causal_swings(tail)
    assert len(swings) >= 4
    summary = summarize(frame, "day", "regular", now, RuleSettings(), demo=False)
    wt = compute_wave_trend(frame, summary)
    assert wt["available"] is True
    assert len(wt["wave"]["pivots"]) >= 4
    assert wt["wave"]["current_wave"] != "待确认"


def test_detect_split_adjustment_and_replace_bars(tmp_path):
    """验证拆股/合股除权因子漂移检测与全量前复权重写自愈。"""
    now = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)
    old_bars = make_bars("SOXX.US", "day", now)[-30:]
    # 模拟常规微小误差（0.1%）不误触发全量重写
    normal_incoming = [{**old_bars[-2], "close": round(old_bars[-2]["close"] * 1.001, 4)}, old_bars[-1]]
    assert Monitor._detect_split_adjustment(old_bars, normal_incoming) is False

    # 模拟 3 拆 1 除权后，重叠交易日前复权收盘价变为原来的 1/3（变动 -66.7% > 0.5%）
    split_incoming = [
        {**old_bars[-2], "close": round(old_bars[-2]["close"] / 3.0, 4)},
        {**old_bars[-1], "close": round(old_bars[-1]["close"] / 3.0, 4)},
    ]
    assert Monitor._detect_split_adjustment(old_bars, split_incoming) is True

    # 验证 Store.replace_bars 原子清空旧数据并写入新前复权序列，且映射到 live-fwd-v3 版本桶
    store = Store(tmp_path)
    store.put_bars("live", "SOXX.US", "day", old_bars)
    assert len(store.bars("live", "SOXX.US", "day")) == len(old_bars)
    rewritten = [{**b, "open": round(b["open"] / 3, 4), "high": round(b["high"] / 3, 4), "low": round(b["low"] / 3, 4), "close": round(b["close"] / 3, 4)} for b in old_bars[-20:]]
    store.replace_bars("live", "SOXX.US", "day", rewritten)
    stored = store.bars("live", "SOXX.US", "day")
    assert len(stored) == 20
    assert stored[-1]["close"] == pytest.approx(old_bars[-1]["close"] / 3, rel=1e-3)
    sources = {r[0] for r in store.db.execute("SELECT DISTINCT source FROM bars").fetchall()}
    assert sources == {"live-fwd-v3"}


@pytest.mark.asyncio
async def test_live_evaluation_intraday_computes_provisional_metrics_without_polluting_confirmed(
    tmp_path, monkeypatch
):
    """验证盘中实时试算复用完整规则引擎产出指标/评级/波浪变化，同时绝不污染已确认收盘日线、正式评分与数据库。"""
    now = datetime(2026, 11, 23, 16, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("signaldesk.service.utcnow", lambda: now)

    store = Store(tmp_path)
    monitor = Monitor(store)
    monitor.settings.mode = "live"
    alloc = Allocation(symbol="NVDA.US", watch_only=True)
    monitor.store.set("portfolio:live", [alloc.model_dump()])
    bars = make_bars("NVDA.US", "day", now)[-260:]
    monitor.store.replace_bars("live", "NVDA.US", "day", bars)
    monitor.rebuild("NVDA.US", initial=True, mode="live")

    last_close = float(bars[-1]["close"])
    surge_price = round(last_close * 1.18, 2)
    await monitor._quote(
        "NVDA.US",
        {
            "last": surge_price,
            "prev_close": last_close,
            "open": round(last_close * 1.12, 2),
            "high": round(last_close * 1.20, 2),
            "low": round(last_close * 1.10, 2),
            "volume": 95_000_000,
            "turnover": 15_000_000_000.0,
            "timestamp": now.isoformat(),
            "trade_status": "Normal",
            "session": "regular",
        },
    )

    detail = monitor.detail_for("NVDA.US", "day", "regular")
    live_eval = detail["live_eval"]
    assert live_eval["available"] is True
    assert live_eval["basis_kind"] == "regular_live"
    assert live_eval["price"] == pytest.approx(surge_price, abs=1e-2)
    assert live_eval["change_pct"] == pytest.approx(18.0, abs=0.2)
    assert live_eval["summary"]["valid"] is True
    assert live_eval["summary"]["close"] == pytest.approx(surge_price, abs=1e-2)
    assert live_eval["forecast"]["rating"]["available"] is True
    assert live_eval["wave_trend"]["available"] is True
    assert live_eval["live_row"] is not None
    assert live_eval["live_row"]["ma20"] is not None
    assert live_eval["live_row"]["rsi"] is not None

    # 严格零污染断言：数据库 K 线条数、正式日线收盘价、正式 summary 不被试算改写
    assert len(monitor.store.bars("live", "NVDA.US", "day")) == 260
    assert detail["summary"]["close"] == pytest.approx(last_close, abs=1e-2)
    assert detail["stock"]["primary"]["close"] == pytest.approx(last_close, abs=1e-2)
    await monitor.stop()


@pytest.mark.asyncio
async def test_live_evaluation_falls_back_to_extended_hours_with_liquidity_flag(
    tmp_path, monkeypatch
):
    """非盘中时段若存在盘前/盘后/夜盘新鲜价格，实时试算自动回退至盘外参考价并标注流动性状态。"""
    # 美东 2026-11-23 07:30（盘前）= 12:30 UTC
    pre_now = datetime(2026, 11, 23, 12, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("signaldesk.service.utcnow", lambda: pre_now)

    store = Store(tmp_path)
    monitor = Monitor(store)
    monitor.settings.mode = "live"
    alloc = Allocation(symbol="SOXX.US", watch_only=True)
    monitor.store.set("portfolio:live", [alloc.model_dump()])
    bars = make_bars("SOXX.US", "day", pre_now)[-260:]
    monitor.store.replace_bars("live", "SOXX.US", "day", bars)
    monitor.rebuild("SOXX.US", initial=True, mode="live")

    last_close = float(bars[-1]["close"])
    pre_price = round(last_close * 1.07, 2)
    await monitor._extended_quote(
        "SOXX.US",
        "pre",
        {
            "last": pre_price,
            "prev_close": last_close,
            "high": round(pre_price * 1.01, 2),
            "low": round(pre_price * 0.99, 2),
            "volume": 2_500,
            "turnover": 450_000.0,  # < $1M，流动性偏薄
            "timestamp": pre_now.isoformat(),
        },
    )

    ev = monitor.live_evaluation_for("SOXX.US", now=pre_now)
    assert ev["available"] is True
    assert ev["basis_kind"] == "ext_pre"
    assert "盘前" in ev["basis_label"]
    assert ev["liquid"] is False
    assert "偏薄" in ev["disclaimer"]
    assert ev["price"] == pytest.approx(pre_price, abs=1e-2)
    assert len(monitor.store.bars("live", "SOXX.US", "day")) == 260
    await monitor.stop()
