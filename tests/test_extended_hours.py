from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from signaldesk.app import create_app
from signaldesk.extended_hours import summarize_extended_hours
from signaldesk.models import Allocation
from signaldesk.service import Monitor
from signaldesk.storage import Store


def test_pre_market_active_over_older_post_and_overnight():
    now = datetime(2026, 11, 23, 10, 15, 0, tzinfo=timezone.utc)
    quote = {
        "last": 125.53,
        "prev_close": 145.98,
        "timestamp": "2026-11-20T21:00:00+00:00",
        "extended": {
            "post": {
                "last": 130.03,
                "prev_close": 125.53,
                "high": 130.73,
                "low": 125.5,
                "volume": 27_299_538,
                "turnover": 3_466_579_251.5,
                "timestamp": "2026-11-21T00:59:59+00:00",
            },
            "overnight": {
                "last": 135.39,
                "prev_close": 125.53,
                "high": 135.79,
                "low": 130.01,
                "volume": 4_050_738,
                "turnover": 541_122_051.0,
                "timestamp": "2026-11-23T09:00:00+00:00",
            },
            "pre": {
                "last": 136.33,
                "prev_close": 125.53,
                "high": 138.0,
                "low": 133.94,
                "volume": 4_203_485,
                "turnover": 571_086_454.35,
                "timestamp": "2026-11-23T10:11:25+00:00",
            },
        },
    }
    ext = summarize_extended_hours(
        quote,
        {"session": "pre", "label": "盘前"},
        {"stop": None, "target": None, "close": 125.53},
        None,
        None,
        now,
    )
    assert ext["available"] is True
    assert ext["is_live_session"] is True
    assert ext["active_session"] == "pre"
    assert ext["active_label"] == "盘前"
    assert ext["price"] == 136.33
    assert ext["gap_pct"] == 8.6
    assert ext["liquid"] is True
    assert ext["liquidity_label"] == "放量充分"
    assert ext["alert_level"] == "positive"
    assert any("大幅高开" in t for t in ext["triggers"])
    assert set(ext["sessions"].keys()) == {"overnight", "pre", "post"}
    assert ext["sessions"]["pre"]["is_fresh"] is True
    assert ext["sessions"]["overnight"]["is_fresh"] is True


def test_thin_liquidity_downgrades_major_gap_and_stop_breach_to_info():
    now = datetime(2026, 11, 23, 10, 15, 0, tzinfo=timezone.utc)
    quote = {
        "last": 100.0,
        "timestamp": "2026-11-20T21:00:00+00:00",
        "extended": {
            "pre": {
                "last": 91.5,
                "prev_close": 100.0,
                "volume": 2_700,
                "turnover": 247_050.0,  # < $100 万，成交偏薄
                "timestamp": "2026-11-23T10:10:00+00:00",
            }
        },
    }
    ext = summarize_extended_hours(
        quote,
        {"session": "pre", "label": "盘前"},
        {"stop": 95.0, "target": 120.0, "close": 100.0},
        None,
        None,
        now,
    )
    assert ext["liquid"] is False
    assert ext["liquidity_label"] == "成交偏薄"
    # 严禁薄流动性小单报出 danger/warning 强预警
    assert ext["alert_level"] == "info"
    assert any("流动性偏薄" in t for t in ext["triggers"])


def test_liquid_gap_triggers_stop_target_and_wave_invalidation_prealerts():
    now = datetime(2026, 11, 23, 10, 15, 0, tzinfo=timezone.utc)
    base_quote = {
        "last": 100.0,
        "timestamp": "2026-11-20T21:00:00+00:00",
    }

    # 1. 放量跌破计划失效价
    q_stop = {
        **base_quote,
        "extended": {
            "pre": {
                "last": 94.0,
                "prev_close": 100.0,
                "turnover": 18_000_000.0,
                "timestamp": "2026-11-23T10:12:00+00:00",
            }
        },
    }
    ext_stop = summarize_extended_hours(
        q_stop,
        {"session": "pre"},
        {"stop": 95.0, "target": 120.0, "close": 100.0},
        {"trend": {"direction": "uptrend", "invalidation_level": 96.0}},
        None,
        now,
    )
    assert ext_stop["alert_level"] == "danger"
    assert any("跌破计划失效价" in t for t in ext_stop["triggers"])
    assert any("跌破波浪前低失效位" in t for t in ext_stop["triggers"])

    # 2. 放量站上空头波浪前高反转位 + 触及计划目标价
    q_target = {
        **base_quote,
        "extended": {
            "overnight": {
                "last": 112.0,
                "prev_close": 100.0,
                "turnover": 25_000_000.0,
                "timestamp": "2026-11-23T06:00:00+00:00",
            }
        },
    }
    ext_target = summarize_extended_hours(
        q_target,
        {"session": "overnight"},
        {"stop": 90.0, "target": 110.0, "close": 100.0},
        {"trend": {"direction": "downtrend", "invalidation_level": 108.0}},
        None,
        now,
    )
    assert ext_target["active_session"] == "overnight"
    assert any("计划目标价" in t for t in ext_target["triggers"])
    assert any("站上波浪前高反转位" in t for t in ext_target["triggers"])


def test_regular_session_suppresses_live_extended_alerts():
    now = datetime(2026, 11, 23, 15, 30, 0, tzinfo=timezone.utc)
    quote = {
        "last": 135.0,
        "timestamp": "2026-11-23T15:29:50+00:00",
        "extended": {
            "pre": {
                "last": 136.33,
                "prev_close": 125.53,
                "turnover": 571_000_000.0,
                "timestamp": "2026-11-23T14:29:59+00:00",
            }
        },
    }
    ext = summarize_extended_hours(
        quote,
        {"session": "regular", "label": "盘中"},
        {"stop": 130.0, "target": 150.0, "close": 135.0},
        None,
        None,
        now,
    )
    assert ext["available"] is True
    assert ext["is_live_session"] is False
    assert ext["alert_level"] == "none"
    assert ext["triggers"] == []


def test_extended_quote_push_never_overwrites_regular_price_or_rating(tmp_path):
    store = Store(tmp_path)
    monitor = Monitor(store)
    monitor.prepare_demo()
    nvda = next(a for a in monitor.portfolio("demo") if a.symbol == "NVDA.US")
    before = monitor.stock(nvda)

    # 模拟在实盘模式下收到常规主价 + 剧烈盘前/夜盘推送（含乱序旧包）
    monitor.settings.mode = "live"
    store.set("portfolio:live", [Allocation(symbol="NVDA.US", name="NVIDIA").model_dump()])
    monitor.frames[("live", "NVDA.US", "day")] = monitor.frames[("demo", "NVDA.US", "day")]
    monitor.summaries[("live", "NVDA.US", "day", "regular")] = monitor.summaries[
        ("demo", "NVDA.US", "day", "regular")
    ]
    monitor.quotes[("live", "NVDA.US")] = {
        "last": 140.0,
        "prev_close": 142.0,
        "timestamp": "2026-11-20T21:00:00+00:00",
        "trade_status": "Normal",
        "session": "regular",
    }

    async def push():
        await monitor._extended_quote(
            "NVDA.US",
            "pre",
            {"last": 162.5, "turnover": 90_000_000.0, "timestamp": "2026-11-23T10:15:00+00:00"},
        )
        # 乱序更旧的盘前推送不得覆写更新的 162.5
        await monitor._extended_quote(
            "NVDA.US",
            "pre",
            {"last": 110.0, "turnover": 50_000_000.0, "timestamp": "2026-11-23T10:05:00+00:00"},
        )

    asyncio.run(push())
    q_live = monitor.quotes[("live", "NVDA.US")]
    assert q_live["last"] == 140.0  # 常规主价严禁被盘前覆盖
    assert q_live["extended"]["pre"]["last"] == 162.5  # 乱序包未回退

    # 切回 demo 校验盘外极端改动不影响技术分与 5 级评级
    monitor.settings.mode = "demo"
    monitor.quotes[("demo", "NVDA.US")]["extended"] = {
        "pre": {
            "last": before["long_plan"]["close"] * 0.72,
            "prev_close": before["long_plan"]["close"],
            "turnover": 500_000_000.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    after = monitor.stock(nvda)
    assert after["primary"]["score"] == before["primary"]["score"]
    assert after["forecast"]["rating"]["score"] == before["forecast"]["rating"]["score"]
    assert after["wave_trend"]["trend"]["direction"] == before["wave_trend"]["trend"]["direction"]


def test_api_bootstrap_and_safe_snapshot_expose_extended_hours_without_private_leaks(tmp_path):
    app = create_app(tmp_path, background=False)
    with TestClient(app) as client:
        boot = client.get("/api/bootstrap")
        assert boot.status_code == 200
        nvda = next(s for s in boot.json()["stocks"] if s["symbol"] == "NVDA.US")
        assert "extended_hours" in nvda
        assert nvda["extended_hours"]["available"] is True

        prev = client.get("/api/analysis/preview/NVDA.US")
        assert prev.status_code == 200
        snap = prev.json()
        assert snap["extended_hours"]["available"] is True
        assert snap["extended_hours"]["price"] is not None
        for secret_key in ("cost_price", "broker_quantity", "long_quantity", "net_assets"):
            assert secret_key not in snap
