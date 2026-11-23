from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from signaldesk.demo import make_bars
from signaldesk.models import Allocation
from signaldesk.providers import LongPortFeed, probe_fastest_broker_domain
from signaldesk.service import Monitor
from signaldesk.storage import Store


def test_probe_fastest_broker_domain_prefers_faster_cn_and_respects_brand_isolation(monkeypatch):
    latencies = {
        "openapi-quote.longbridge.cn": 140.0,
        "openapi-quote.longbridge.com": 2400.0,
        "openapi-quote.longportapp.cn": 180.0,
        "openapi-quote.longportapp.com": 1950.0,
    }
    monkeypatch.setattr("signaldesk.providers._tcp_latency_ms", lambda host, port=443, timeout=1.5: latencies.get(host))

    assert probe_fastest_broker_domain("longbridge") == "longbridge.cn"
    assert probe_fastest_broker_domain("longbridge", exclude="longbridge.cn") == "longbridge.com"
    assert probe_fastest_broker_domain("longport") == "longportapp.cn"

    # 严禁跨品牌传入域名
    with pytest.raises(ValueError, match="不匹配"):
        LongPortFeed(
            {"platform": "longport", "app_key": "k", "app_secret": "s", "access_token": "t"},
            lambda x: None,
            domain="longbridge.cn",
        )


@pytest.mark.asyncio
async def test_create_feed_with_fallback_switches_to_backup_domain_on_failure(tmp_path, monkeypatch):
    monitor = Monitor(Store(tmp_path))
    tried: list[str] = []

    def fake_probe(platform="longport", timeout=1.5, exclude=None):
        return "longbridge.com" if exclude == "longbridge.cn" else "longbridge.cn"

    class FakeFeed:
        def __init__(self, creds, emit, domain=None):
            tried.append(domain)
            if domain == "longbridge.cn":
                raise RuntimeError("cn timeout")
            self.domain = domain
            self.renew_at = None

        def close(self):
            pass

    monkeypatch.setattr("signaldesk.service.probe_fastest_broker_domain", fake_probe)
    monkeypatch.setattr("signaldesk.service.LongPortFeed", FakeFeed)

    try:
        feed = await monitor._create_feed_with_fallback({"platform": "longbridge", "access_token": "t"})
        assert tried == ["longbridge.cn", "longbridge.com"]
        assert feed.domain == "longbridge.com"
        assert monitor.broker_domain == "longbridge.com"
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_connect_fetches_quotes_before_history_and_skips_synced_daily_backfill(tmp_path, monkeypatch):
    # 2026-11-23 16:00 UTC = 美东 11:00 常规盘中，最近已完成常规日线为 2026-11-20
    now = datetime(2026, 11, 23, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("signaldesk.service.utcnow", lambda: now)

    store = Store(tmp_path)
    monitor = Monitor(store)
    monitor.settings.mode = "live"
    monitor.store.set("portfolio:live", [Allocation(symbol="NVDA.US", watch_only=True).model_dump()])
    bars = make_bars("NVDA.US", "day", now)[-260:]
    monitor.store.put_bars("live", "NVDA.US", "day", bars)
    monitor.rebuild("NVDA.US", initial=True, mode="live")

    call_order: list[str] = []
    history_calls: list[tuple[str, bool]] = []

    class FakeFeed:
        domain = "longbridge.cn"
        renew_at = None
        symbols: set[str] = set()

        def account(self):
            call_order.append("account")
            return {"positions": [], "cash": None, "net_assets": None, "unsupported": []}

        def quotes(self, symbols):
            call_order.append("quotes")
            return [
                {
                    "symbol": "NVDA.US",
                    "quote": {
                        "last": 165.0,
                        "prev_close": 150.0,
                        "timestamp": now.isoformat(),
                        "trade_status": "Normal",
                        "session": "regular",
                    },
                }
            ]

        def subscribe(self, symbols):
            call_order.append("subscribe")
            self.symbols.update(symbols)

        def valuations(self, symbols):
            call_order.append("valuations")
            return {"NVDA.US": {"pe_ttm": 25.0, "pb": 10.0, "dividend_yield_pct": 0.1, "fetched_at": now.isoformat()}}

        def history(self, symbol, timeframe, initial=False):
            history_calls.append((symbol, initial))
            return bars[-5:]

        def market_calendar(self):
            return {"trade_days": [], "half_trade_days": [], "session_metadata_available": True}

        def close(self):
            pass

    monkeypatch.setattr(monitor.vault, "configured", lambda svc: svc == "longport")

    async def fake_creds():
        return {"platform": "longbridge", "method": "oauth", "client_id": "c", "access_token": "t"}

    async def fake_create(creds):
        monitor.broker_domain = "longbridge.cn"
        return FakeFeed()

    monkeypatch.setattr(monitor.oauth, "credentials", fake_creds)
    monkeypatch.setattr(monitor, "_create_feed_with_fallback", fake_create)
    monkeypatch.setattr(monitor, "_sync_macro_benchmarks", lambda: _noop())

    try:
        await monitor._connect()
        if monitor.history_backfill_task:
            await monitor.history_backfill_task
        # 验证 quotes 在 subscribe 之前立刻拉取，且已缓存完整的 NVDA 日线不再重复拉 1000 根历史
        assert call_order[:3] == ["account", "quotes", "subscribe"]
        assert history_calls == []
        nvda_item = monitor.stock(monitor.portfolio("live")[0])
        assert nvda_item["quote"]["last"] == 165.0
        assert nvda_item["quote"]["prev_close"] == 150.0
        assert nvda_item["change_percent"] == pytest.approx(10.0)

        # 盘中例行轮询 skip_synced_daily=True 时同样不重复拉取已对齐的日线
        await monitor._poll(skip_synced_daily=True)
        assert history_calls == []
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_intraday_push_without_prev_close_falls_back_to_cached_daily_close(tmp_path, monkeypatch):
    now = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("signaldesk.service.utcnow", lambda: now)

    monitor = Monitor(Store(tmp_path))
    monitor.settings.mode = "live"
    alloc = Allocation(symbol="AAPL.US", watch_only=True)
    monitor.store.set("portfolio:live", [alloc.model_dump()])
    bars = make_bars("AAPL.US", "day", now)[-260:]
    monitor.store.put_bars("live", "AAPL.US", "day", bars)
    monitor.rebuild("AAPL.US", initial=True, mode="live")
    prev_day_close = float(bars[-1]["close"])

    # 模拟跨交易日：旧报价是上一交易日，盘中实时推送无 prev_close 字段
    monitor.quotes[("live", "AAPL.US")] = {
        "last": prev_day_close,
        "prev_close": float(bars[-2]["close"]),
        "timestamp": "2026-11-20T21:00:00+00:00",
        "trade_status": "Normal",
        "session": "regular",
    }
    try:
        await monitor._quote(
            "AAPL.US",
            {
                "last": round(prev_day_close * 1.05, 2),
                "timestamp": now.isoformat(),
                "trade_status": "Normal",
                "session": "regular",
            },
        )
        stock = monitor.stock(alloc)
        assert stock["quote"]["prev_close"] == pytest.approx(prev_day_close)
        assert stock["change_percent"] == pytest.approx(5.0, abs=0.1)
        assert monitor.quote_resync_needed is True
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_start_live_seeds_reference_quotes_from_cached_daily_bars(tmp_path, monkeypatch):
    now = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("signaldesk.service.utcnow", lambda: now)

    store = Store(tmp_path)
    store.set("settings", {"mode": "live"})
    alloc = Allocation(symbol="MSFT.US", watch_only=True)
    store.set("portfolio:live", [alloc.model_dump()])
    bars = make_bars("MSFT.US", "day", now)[-260:]
    store.put_bars("live", "MSFT.US", "day", bars)

    monitor = Monitor(store)
    try:
        await monitor.start(background=False)
        item = monitor.stock(alloc)
        assert item["quote"]["seeded"] is True
        assert item["quote"]["last"] == pytest.approx(float(bars[-1]["close"]))
        assert item["quote"]["prev_close"] == pytest.approx(float(bars[-2]["close"]))
        assert item["change_percent"] is not None
    finally:
        await monitor.stop()


async def _noop():
    return SimpleNamespace()
