from datetime import date, datetime, timedelta, timezone
from inspect import signature
from types import SimpleNamespace
from unittest.mock import Mock

import longbridge.openapi as lp
import pandas as pd
import pytest

from signaldesk.calendar import NY, bar_end
from signaldesk.demo import make_bars
from signaldesk.indicators import chart_rows, enrich, summarize
from signaldesk.models import Allocation, RuleSettings
from signaldesk.providers import LongPortFeed, normalize_bar
from signaldesk.research import (
    fetch_comex_gold,
    gold_context,
    parse_eastmoney_comex_gold,
    parse_yahoo_comex_gold,
    research_context,
    treasury_observations,
)
from signaldesk.security import safe_snapshot
from signaldesk.service import Monitor
from signaldesk.storage import Store


@pytest.mark.parametrize("platform,domain", [(None, "longportapp.com"), ("longbridge", "longbridge.com")])
def test_broker_uses_only_selected_issuer_endpoints(monkeypatch, platform, domain):
    config = Mock()
    monkeypatch.setattr(lp, "Config", config)
    monkeypatch.setattr(lp, "QuoteContext", Mock())
    monkeypatch.setattr(lp, "TradeContext", Mock())
    credentials = dict(app_key=" key ", app_secret="secret", access_token=" token ")
    if platform:
        credentials["platform"] = platform
    LongPortFeed(credentials, Mock())
    args, options = config.from_apikey.call_args
    assert args == ("key", "secret", "token")
    assert options["http_url"] == f"https://openapi.{domain}"
    assert options["quote_ws_url"] == f"wss://openapi-quote.{domain}/v2"
    assert options["trade_ws_url"] == f"wss://openapi-trade.{domain}/v2"


def test_quote_subscription_matches_installed_sdk():
    calls = []
    sdk_signature = signature(lp.QuoteContext.subscribe)

    def subscribe(*args, **kwargs):
        bound = sdk_signature.bind(None, *args, **kwargs)
        calls.append((bound.arguments["symbols"], bound.arguments["sub_types"]))

    feed = LongPortFeed.__new__(LongPortFeed)
    feed.lp = lp
    feed.symbols = set()
    feed.quote_context = SimpleNamespace(subscribe=subscribe)
    feed.subscribe(["TEST.US"])
    feed.subscribe(["TEST.US"])
    assert calls == [(["TEST.US"], [lp.SubType.Quote])]


def test_public_spy_half_day_history_and_confirmed_upsert(tmp_path):
    # Longbridge history by date, SPY.US, Intraday/Day/NoAdjust, 2025-11-28.
    opening = datetime(2025, 11, 28, tzinfo=NY)
    raw = SimpleNamespace(
        timestamp=datetime.fromtimestamp(opening.timestamp()),
        open="680.86",
        high="683.665",
        low="680.5",
        close="683.39",
        volume="49973521",
        turnover="34098587619.881",
        trade_session="Intraday",
    )
    bar = normalize_bar(raw, "day")
    assert bar["timestamp"] == "2025-11-28T05:00:00+00:00"
    close_time = bar_end(datetime.fromisoformat(bar["timestamp"]), "day")
    assert close_time.isoformat() == "2025-11-28T18:00:00+00:00"
    store = Store(tmp_path)
    store.put_bars("live", "SPY.US", "day", [bar, {**bar, "confirmed": False, "close": 680}])
    stored = store.bars("live", "SPY.US", "day")
    assert stored == [bar] and not store.bars("demo", "SPY.US", "day")
    assert enrich(stored, "day", close_time - timedelta(seconds=1), RuleSettings()).empty
    frame = enrich(stored, "day", close_time, RuleSettings())
    row = chart_rows(frame, "regular")[0]
    assert [row[k] for k in ("open", "high", "low", "close", "volume", "turnover")] == [
        680.86,
        683.665,
        680.5,
        683.39,
        49973521,
        34098587619.881,
    ]
    summary = summarize(frame, "day", "regular", close_time, RuleSettings())
    assert summary["close"] == row["close"] and summary["as_of"] == close_time.isoformat()
    assert summary["confirmed_price_available"] and not summary["valid"]
    store.close()


def test_daily_gaps_reset_and_contributions_reconcile():
    now = datetime(2026, 11, 18, 22, tzinfo=timezone.utc)
    bars = make_bars("AAPL.US", "day", now)[-300:]
    frame = enrich(bars, "day", now, RuleSettings())
    summary = summarize(frame, "day", "regular", now, RuleSettings())
    assert sum(summary["contributions"].values()) == pytest.approx(summary["score"])
    assert sum(summary["contribution_changes"].values()) == pytest.approx(frame.score.diff().iloc[-1])
    assert pd.isna(enrich(bars[:-10] + bars[-9:], "day", now, RuleSettings()).score.iloc[-1])


@pytest.mark.asyncio
@pytest.mark.parametrize(("missed", "unavailable"), [(1, False), (12, False), (12, True)])
async def test_poll_recovers_sessions_after_sleep(tmp_path, monkeypatch, missed, unavailable):
    now = datetime(2026, 11, 18, 22, tzinfo=timezone.utc)
    monkeypatch.setattr("signaldesk.service.utcnow", lambda: now)
    bars = make_bars("AAPL.US", "day", now)[-300:]
    monitor = Monitor(Store(tmp_path))
    monitor.settings.mode = "live"
    monitor.store.set("portfolio:live", [Allocation(symbol="AAPL", watch_only=True).model_dump()])
    monitor.store.put_bars("live", "AAPL.US", "day", bars[:-missed])
    monitor.rebuild("AAPL.US", initial=True)
    requests = []

    def history(symbol, timeframe, initial=False):
        assert (symbol, timeframe) == ("AAPL.US", "day")
        requests.append(initial)
        if initial:
            return bars[:-9] + bars[-8:] if unavailable else bars
        return bars[-5:]

    monitor.feed = SimpleNamespace(
        symbols={"AAPL.US"},
        history=history,
        subscribe=lambda symbols: None,
        account=lambda: {"positions": [], "cash": None, "net_assets": None, "unsupported": []},
        valuations=lambda symbols: {},
        quotes=lambda symbols: [],
        close=lambda: None,
    )
    try:
        await monitor._poll()
        assert requests == ([False, True] if missed > 5 else [False])
        cached = monitor.store.bars("live", "AAPL.US", "day")
        assert len(cached) == (299 if unavailable else 300)
        summary = monitor.detail_for("AAPL.US", "day", "regular")["summary"]
        assert summary["valid"] == (not unavailable)
        assert summary["close"] == bars[-1]["close"]
        if missed > 5:
            assert monitor.store.events("live") == []
            assert monitor.store.deliveries() == []
        await monitor._poll()
        assert requests == ([False, True, False] if missed > 5 else [False, False])
        assert monitor.store.bars("live", "AAPL.US", "day") == cached
        if unavailable:
            unavailable = False
            monitor.history_retry_at["AAPL.US"] = 0
            await monitor._poll()
            assert requests[-2:] == [False, True]
            assert monitor.detail_for("AAPL.US", "day", "regular")["summary"]["valid"]
            assert monitor.store.events("live") == []
    finally:
        await monitor.stop()


def test_curve_observations_and_valuation_with_dated_sources():
    xml = b"""<feed xmlns:d="urn:d"><d:properties><d:NEW_DATE>2025-11-28T00:00:00</d:NEW_DATE>
      <d:BC_2YEAR>3.4</d:BC_2YEAR><d:BC_10YEAR>4.0</d:BC_10YEAR></d:properties>
      <d:properties><d:NEW_DATE>2025-11-27</d:NEW_DATE><d:BC_10YEAR>3.1</d:BC_10YEAR></d:properties>
      <d:properties><d:NEW_DATE>2025-12-01</d:NEW_DATE><d:BC_10YEAR>4</d:BC_10YEAR>
      <d:BC_2YEAR>3</d:BC_2YEAR></d:properties></feed>"""
    assert treasury_observations(xml, date(2025, 11, 28)) == {"2025-11-28": (3.4, 4)}
    now = datetime(2025, 11, 28, 22, tzinfo=timezone.utc)
    val = {"pe_ttm": 25, "fetched_at": now.isoformat()}
    curve = {"as_of": "2025-11-28", "ten_year": 4}
    review = research_context(val, curve, now, False)
    assert review["earnings_yield_pct"] == 4 and review["yield_gap_pp"] == 0
    assert research_context(val, curve, now + timedelta(days=8), False)["yield_gap_pp"] is None
    assert research_context({**val, "pe_ttm": -2}, curve, now, False)["earnings_yield_pct"] is None
    assert research_context(val, {}, now, False)["yield_gap_pp"] is None


@pytest.mark.asyncio
async def test_long_plan_never_inherits_mixed_tactical_levels(tmp_path):
    monitor = Monitor(Store(tmp_path))
    mixed = Allocation(symbol="ABC", long_quantity=2, short_quantity=3, broker_quantity=5, stop_price=90)
    assert mixed.long_levels() == (None, None)
    monitor.store.set("portfolio:demo", [mixed.model_dump()])
    newer = monitor.save_allocation(mixed.model_copy(update={"long_target_price": 105}))
    monitor.summaries["demo", "ABC.US", "day", "regular"] = {
        "valid": False,
        "score": None,
        "state": "unavailable",
        "confirmed_price_available": True,
        "close": 106,
        "risks": ["预热"],
        "as_of": "2026-11-18T21:00:00+00:00",
    }
    stock = monitor.stock(newer)
    assert stock["primary_key"] == "day:regular" and stock["long_plan"]["status"] == "复核计划目标价"
    assert stock["stop_price"] == 90 and stock["long_plan"]["stop"] is None
    preview = safe_snapshot(stock, "demo")
    assert list(preview["technical"]) == ["day:regular"]
    assert preview["long_plan"]["target_distance_percent"] == pytest.approx((106 / 105 - 1) * 100)
    assert Allocation(symbol="OLD", long_quantity=1, broker_quantity=1, stop_price=85).long_levels() == (
        85,
        None,
    )
    assert Allocation(symbol="NEW", watch_only=True).sleeves() == ["long"]
    await monitor.stop()


@pytest.mark.asyncio
async def test_longport_watchlist_sync_merges_groups_and_preserves_favorites(tmp_path, monkeypatch):
    now = datetime(2026, 11, 18, 22, tzinfo=timezone.utc)
    monkeypatch.setattr("signaldesk.service.utcnow", lambda: now)
    feed = LongPortFeed.__new__(LongPortFeed)
    feed.lp = lp
    feed.symbols = set()
    groups = [
        SimpleNamespace(
            id=1,
            name="AI 与算力",
            securities=[
                SimpleNamespace(symbol="NVDA.US", name="英伟达"),
                SimpleNamespace(symbol="AMD.US", name="超威半导体"),
                SimpleNamespace(symbol="00700.HK", name="腾讯控股"),
                SimpleNamespace(symbol="600519.SH", name="贵州茅台"),
                SimpleNamespace(symbol="000001.SZ", name="平安银行"),
                SimpleNamespace(symbol="INVALID!", name="bad"),
            ],
        ),
        SimpleNamespace(
            id=2,
            name="核心持仓",
            securities=[
                SimpleNamespace(symbol="NVDA.US", name="英伟达"),
                SimpleNamespace(symbol="TSLA.US", name="特斯拉"),
            ],
        ),
    ]
    feed.quote_context = SimpleNamespace(watchlist=lambda: groups)
    parsed = feed.watchlist()
    assert len(parsed["groups"]) == 2
    assert parsed["unsupported"] == ["INVALID!"]
    assert "00700.HK" in parsed["groups"][0]["symbols"]
    nvda_entry = next(s for s in parsed["securities"] if s["symbol"] == "NVDA.US")
    assert nvda_entry["groups"] == ["AI 与算力", "核心持仓"]

    monitor = Monitor(Store(tmp_path))
    monitor.settings.mode = "live"
    monitor.feed = SimpleNamespace(
        symbols=set(),
        account=lambda: {
            "positions": [
                {
                    "symbol": "NVDA.US",
                    "name": "英伟达",
                    "broker_quantity": 10.0,
                    "available_quantity": 10.0,
                    "cost_price": 120.0,
                }
            ],
            "net_assets": 50000.0,
            "cash": 20000.0,
            "unsupported": [],
        },
        watchlist=lambda: parsed,
        history=lambda symbol, timeframe, initial=False: [],
        subscribe=lambda symbols: None,
        quotes=lambda symbols: [],
        valuations=lambda symbols: {},
        close=lambda: None,
    )
    await monitor._sync_account()
    live_items = {a.symbol: a for a in monitor.portfolio("live")}
    assert set(live_items) == {"NVDA.US", "AMD.US", "TSLA.US", "00700.HK", "600519.SH", "000001.SZ"}
    assert live_items["NVDA.US"].broker_quantity == 10 and live_items["NVDA.US"].in_watchlist
    assert live_items["AMD.US"].watch_only and live_items["AMD.US"].watchlist_groups == ["AI 与算力"]
    assert monitor.watchlist_unsupported == ["INVALID!"]

    # Favorite TSLA locally, leave AMD unfavorited & without stop/target; then remove both from broker watchlist.
    monitor.set_favorite("TSLA.US", True)
    monitor.feed.watchlist = lambda: {"groups": [], "securities": [], "unsupported": []}
    result = await monitor.sync_watchlist_now()
    assert result["ok"] is True
    after_items = {a.symbol: a for a in monitor.portfolio("live")}
    assert "NVDA.US" in after_items and not after_items["NVDA.US"].in_watchlist
    assert "TSLA.US" in after_items and after_items["TSLA.US"].favorite and not after_items["TSLA.US"].in_watchlist
    assert "AMD.US" not in after_items

    # Verify deterministic verdict outputs across stop/target/reconciliation/held/watch states.
    now = datetime(2026, 11, 18, 22, tzinfo=timezone.utc)
    bars = make_bars("NVDA.US", "day", now)[-260:]
    monitor.store.put_bars("live", "NVDA.US", "day", bars)
    monitor.rebuild("NVDA.US", initial=True, mode="live")
    base_close = monitor.summaries[("live", "NVDA.US", "day", "regular")]["close"]
    nvda_alloc = monitor.save_allocation(
        Allocation(
            symbol="NVDA.US",
            long_quantity=10,
            broker_quantity=10,
            long_stop_price=base_close + 5,
            long_target_price=base_close + 25,
        )
    )
    stop_verdict = monitor.stock(nvda_alloc)["verdict"]
    assert stop_verdict["action"] == "跌破止损" and stop_verdict["tone"] == "danger"
    assert stop_verdict["action_meaning"]
    assert stop_verdict["priority"] == 0 and len(stop_verdict["pillars"]) == 3
    assert set(stop_verdict["dimension_notes"]) == {"trend", "momentum", "volume_score"}

    nvda_target = monitor.save_allocation(
        Allocation(
            symbol="NVDA.US",
            long_quantity=10,
            broker_quantity=10,
            long_stop_price=max(1.0, base_close - 25),
            long_target_price=max(2.0, base_close - 2),
        )
    )
    target_verdict = monitor.stock(nvda_target)["verdict"]
    assert target_verdict["action"] == "触及目标" and target_verdict["tone"] == "warning"
    assert target_verdict["priority"] == 1

    unreconciled = Allocation(symbol="NVDA.US", long_quantity=5, broker_quantity=10)
    assert monitor.stock(unreconciled)["verdict"]["action"] == "仓位待核"

    monitor.store.put_bars("live", "TSLA.US", "day", bars)
    monitor.rebuild("TSLA.US", initial=True, mode="live")
    tsla_verdict = monitor.stock(after_items["TSLA.US"])["verdict"]
    assert tsla_verdict["headline"] and tsla_verdict["next_step"]
    await monitor.stop()


def _sample_yahoo_gold_payload(now: datetime) -> dict:
    # 构造 24 个交易日的日线序列，同时故意放入误导性的 chartPreviousClose（2个月前）与未来异常时间戳
    base_day = date(2026, 10, 15)
    timestamps = []
    closes = []
    highs = []
    lows = []
    for i in range(24):
        d = base_day + timedelta(days=i)
        dt = datetime(d.year, d.month, d.day, 18, 0, tzinfo=timezone.utc)
        timestamps.append(int(dt.timestamp()))
        c = 2500.0 + i * 10.0
        closes.append(c)
        highs.append(c + 12.0)
        lows.append(c - 8.0)
    # 末尾附加一条异常远期时间戳，验证会被过滤
    future_dt = now + timedelta(days=10)
    timestamps.append(int(future_dt.timestamp()))
    closes.append(9999.0)
    highs.append(10000.0)
    lows.append(9900.0)
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "USD",
                        "symbol": "GC=F",
                        "exchangeName": "CMX",
                        "fullExchangeName": "COMEX",
                        "regularMarketPrice": 2740.0,
                        "regularMarketDayHigh": 2755.0,
                        "regularMarketDayLow": 2718.0,
                        "regularMarketTime": timestamps[23],
                        "chartPreviousClose": 2300.0,
                    },
                    "timestamp": timestamps,
                    "indicators": {"quote": [{"close": closes, "high": highs, "low": lows}]},
                }
            ]
        }
    }


def _sample_eastmoney_gold_payload() -> dict:
    base_day = date(2026, 10, 15)
    klines = []
    for i in range(24):
        d = (base_day + timedelta(days=i)).isoformat()
        c = 2500.0 + i * 10.0
        klines.append(f"{d},{c - 5:.2f},{c:.2f},{c + 11:.2f},{c - 9:.2f},12000")
    return {"data": {"code": "GC00Y", "name": "COMEX黄金", "klines": klines}}


def test_comex_gold_parsers_and_context_linkage():
    now = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)
    yahoo = parse_yahoo_comex_gold(_sample_yahoo_gold_payload(now), now)
    assert yahoo["exchange"] == "COMEX"
    assert yahoo["price"] == 2740.0
    # 昨收应取倒数第 2 根日线（2720），绝不是 2 个月前的 chartPreviousClose（2300）
    assert yahoo["prev_close"] == 2720.0
    assert yahoo["change_pct"] == pytest.approx((2740.0 / 2720.0 - 1.0) * 100.0, abs=0.01)
    assert yahoo["prior_date"] == "2026-10-17"
    assert yahoo["change_21d_pct"] == pytest.approx((2740.0 / 2520.0 - 1.0) * 100.0, abs=0.01)
    assert yahoo["as_of"] == "2026-11-07"

    em = parse_eastmoney_comex_gold(_sample_eastmoney_gold_payload(), now)
    assert em["symbol"] == "GC00Y"
    assert em["price"] == 2730.0
    assert em["prev_close"] == 2720.0
    assert em["change_21d_pct"] == pytest.approx((2730.0 / 2520.0 - 1.0) * 100.0, abs=0.01)

    ctx = gold_context(yahoo, now, demo=False, real_ten_year=2.05, real_rate_fresh=True)
    assert ctx["available"] is True and ctx["fresh"] is True
    assert "高实际利率下偏强" in ctx["real_rate_linkage"]

    stale_ctx = gold_context(yahoo, now + timedelta(days=9), demo=False, real_ten_year=2.05, real_rate_fresh=True)
    assert stale_ctx["available"] is True and stale_ctx["fresh"] is False

    empty_ctx = gold_context({}, now, demo=False)
    assert empty_ctx["available"] is False and empty_ctx["fresh"] is False and empty_ctx["price"] is None


@pytest.mark.asyncio
async def test_fetch_comex_gold_dual_source_fallback(monkeypatch):
    import httpx

    now = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)
    yahoo_payload = _sample_yahoo_gold_payload(now)
    em_payload = _sample_eastmoney_gold_payload()

    class FakeResp:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("err", request=None, response=self)

        def json(self):
            return self._payload

    calls: list[str] = []

    async def fake_get_yahoo_fallback(self, url, params=None):
        calls.append(url)
        if "query1" in url:
            raise httpx.ConnectTimeout("timeout")
        return FakeResp(200, yahoo_payload)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get_yahoo_fallback)
    res1 = await fetch_comex_gold(now)
    assert res1["source"] == "Yahoo Finance (COMEX)" and len(calls) == 2

    calls.clear()

    async def fake_get_eastmoney_fallback(self, url, params=None):
        calls.append(url)
        if "yahoo.com" in url:
            return FakeResp(429, {})
        return FakeResp(200, em_payload)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get_eastmoney_fallback)
    res2 = await fetch_comex_gold(now)
    assert res2["source"] == "东方财富 (COMEX黄金)" and res2["symbol"] == "GC00Y" and len(calls) == 3

    async def fake_get_all_fail(self, url, params=None):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get_all_fail)
    with pytest.raises(ValueError, match="COMEX 黄金公开行情获取失败"):
        await fetch_comex_gold(now)
