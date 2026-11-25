from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from signaldesk.calendar import bar_end, latest_expected_end, session_for
from signaldesk.instruments import classify_instrument
from signaldesk.markets import CN, HK, US, broker_symbol, normalize_symbol
from signaldesk.models import Allocation
from signaldesk.providers import LongPortFeed
from signaldesk.service import Monitor
from signaldesk.storage import Store


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        (" aapl ", "AAPL.US"),
        ("brk.b", "BRK.B.US"),
        ("00700.hk", "00700.HK"),
        ("700.HK", "00700.HK"),
        ("hsi.hk", "HSI.HK"),
        ("600519.sh", "600519.SH"),
        ("000001.sz", "000001.SZ"),
    ],
)
def test_allocation_symbol(raw, canonical):
    assert Allocation(symbol=raw).symbol == canonical
    assert normalize_symbol(canonical, broker=True) == canonical


def test_hk_wire_code_stays_compatible_with_longbridge():
    assert broker_symbol("00700.HK") == "700.HK"
    assert broker_symbol("HSI.HK") == "HSI.HK"
    assert broker_symbol("000001.SZ") == "000001.SZ"


@pytest.mark.parametrize("raw", ["000001", "AAPL!.HK", "600519.SG", "VOD.L", "900901.SH", "200012.SZ"])
def test_unsupported_security_is_not_assigned_to_another_market(raw):
    with pytest.raises(ValueError):
        Allocation(symbol=raw)


def test_local_session_break_holiday_and_close():
    # A regular trading day in both Asian markets, Thanksgiving in New York.
    noon = datetime(2026, 11, 26, 4, 15, tzinfo=timezone.utc)
    assert session_for(noon, HK)["session"] == session_for(noon, CN)["session"] == "break"
    assert session_for(noon, US)["session"] == "closed"
    assert latest_expected_end(noon, "15m", "regular", HK).hour == 4
    assert latest_expected_end(noon, "15m", "regular", CN).strftime("%H:%M") == "03:30"
    stamp = datetime(2026, 11, 25, 16, tzinfo=timezone.utc)  # midnight in HK / Shanghai
    hk_close = bar_end(stamp, "day", HK)
    cn_close = bar_end(stamp, "day", CN)
    assert hk_close.isoformat() == "2026-11-26T08:10:00+00:00"
    auction = hk_close.replace(minute=8)
    assert session_for(auction, HK)["session"] == "closing_auction"
    assert latest_expected_end(auction, "day", "regular", HK).day == 25
    assert latest_expected_end(hk_close, "day", "regular", HK) == hk_close
    assert cn_close.isoformat() == "2026-11-26T07:00:00+00:00"
    assert latest_expected_end(cn_close, "day", "regular", CN) == cn_close
    assert latest_expected_end(cn_close, "day", "regular", HK).day == 25
    assert session_for(cn_close, HK)["session"] == "regular"
    assert session_for(cn_close, CN)["session"] == "closed"
    half_day = datetime(2025, 12, 24, 5, tzinfo=timezone.utc)
    assert session_for(half_day, HK)["early_close"]
    assert bar_end(half_day, "day", HK).strftime("%H:%M") == "04:10"
    assert session_for(datetime(2026, 10, 1, 2, tzinfo=timezone.utc), CN)["session"] == "closed"
    unknown = datetime(2050, 1, 3, tzinfo=timezone.utc)
    assert session_for(unknown, CN)["session"] == "unknown"
    assert latest_expected_end(unknown, "day", "regular", CN) is None


def test_mixed_positions_use_matching_currency_net_assets(tmp_path):
    feed = LongPortFeed.__new__(LongPortFeed)

    def position(symbol, currency):
        return SimpleNamespace(
            symbol=symbol,
            symbol_name=symbol,
            quantity=10,
            available_quantity=10,
            currency=currency,
            cost_price=80,
        )

    positions = [position("00700.HK", "HKD"), position("700.HK", "HKD"), position("000001.SZ", "CNY")]

    def balances(currency):
        if currency == "CNY":
            raise RuntimeError("unavailable")
        return [
            SimpleNamespace(
                currency=currency, total_cash=500, net_assets=10000 if currency == "USD" else 80000
            )
        ]

    feed.trade_context = SimpleNamespace(
        stock_positions=lambda: SimpleNamespace(channels=[SimpleNamespace(positions=positions)]),
        account_balance=balances,
    )
    account = feed.account()
    assert account["unsupported"] == []
    assert len(account["positions"]) == 2
    store = Store(tmp_path)
    try:
        store.set("account:live", {k: v for k, v in account.items() if k != "positions"})
        monitor = Monitor(store)
        monitor.settings.mode = "live"
        for p in account["positions"]:
            allocation = Allocation(**p)
            monitor.quotes[("live", allocation.symbol)] = {"last": 100}
            stock = monitor.stock(allocation, macro={"risk_gauge": {"red_count": 6}})
            assert stock["currency"] == allocation.currency
            assert stock["pnl_percent"] == 25
            if allocation.currency == "HKD":
                assert stock["symbol"] == "00700.HK" and stock["weight_percent"] == 2.5
            else:
                assert stock["weight_percent"] is None
            assert stock["research"]["yield_gap_pp"] is None
            assert stock["extended_hours"]["available"] is False
    finally:
        store.close()


def test_valuation_permission_failure_isolated_by_market(tmp_path):
    import longbridge.openapi as lp

    feed = LongPortFeed.__new__(LongPortFeed)
    feed.lp = lp

    def indexes(symbols, fields):
        if "000001.SZ" in symbols:
            raise RuntimeError("quote permission unavailable")
        return [SimpleNamespace(symbol=s, pe_ttm_ratio=20, pb_ratio=2, dividend_ratio_ttm=1) for s in symbols]

    profiles = {
        "80700.HK": SimpleNamespace(symbol="80700.HK", currency="CNY", name_cn="腾讯控股-R", board=lp.SecurityBoard.HKEquity),
        "000001.SZ": SimpleNamespace(symbol="000001.SZ", name_cn="平安银行", board=lp.SecurityBoard.SZMainConnect),
    }
    feed.quote_context = SimpleNamespace(
        calc_indexes=indexes,
        static_info=lambda symbols: [profiles[s] for s in symbols],
    )
    updates = feed.valuations(["AAPL.US", "000001.SZ", "80700.HK"])
    assert updates["AAPL.US"]["pe_ttm"] == 20
    assert updates["80700.HK"]["currency"] == "CNY"
    assert updates["000001.SZ"]["refresh_failed"]
    store = Store(tmp_path)
    try:
        monitor = Monitor(store)
        monitor.valuations = {"000001.SZ": {"pe_ttm": 11, "fetched_at": "2025-11-01T00:00:00+00:00"}}
        monitor._save_valuations(updates)
        cached = store.get("valuations:live")["000001.SZ"]
        assert cached["pe_ttm"] == 11
        assert cached["fetched_at"] == "2025-11-01T00:00:00+00:00"
        assert cached["board"] == "SZMainConnect"
        monitor.settings.mode = "live"
        stock = monitor.stock(Allocation(symbol="000001.SZ", name="PING AN BANK"), macro={})
        assert stock["name"] == "平安银行" and stock["instrument"]["asset_type"] == "stock"
    finally:
        store.close()


def test_asian_indices_etfs_and_leveraged_products():
    assert classify_instrument("000001.SH")["asset_type"] == "index"
    assert classify_instrument("000001.SZ")["asset_type"] == "stock"
    assert classify_instrument("HSTECH.HK")["asset_type"] == "index"
    assert classify_instrument("ABC.HK", board="HKHS")["asset_type"] == "index"
    assert classify_instrument("02800.HK", "盈富基金")["is_fund"]
    assert classify_instrument("510300.SH", "沪深300")["is_fund"]
    assert classify_instrument("158001.SZ")["is_fund"]
    assert classify_instrument("07200.HK")["leverage"] == 2
    assert classify_instrument("87500.HK")["leverage"] == -2
    assert classify_instrument("15000.HK", board="HKWarrant")["asset_type"] == "derivative"
    assert classify_instrument("ABC.HK")["asset_type"] == "unknown"


def test_cache_reset_only_once_and_preserves_portfolio(tmp_path):
    bar = {"timestamp": "2026-11-24T00:00:00+00:00", "confirmed": True}
    store = Store(tmp_path)
    store.set("migration:hk-five-digit-v1", False)
    store.set("portfolio:live", [{"symbol": "700.HK", "favorite": True, "long_stop_price": 400}])
    store.set("watchlist-groups:live", [{"name": "港股", "symbols": ["700.HK"]}])
    store.set("valuations:live", {"700.HK": {"currency": "HKD"}})
    store.set("state:live:700.HK:long:day:regular", {"last_sent": 1})
    for symbol in ("700.HK", "000001.SZ", "600519.SH", "AAPL.US"):
        store.put_bars("live", symbol, "day", [bar])
    store.close()

    store = Store(tmp_path)
    try:
        assert store.get("portfolio:live") == [{"symbol": "00700.HK", "favorite": True, "long_stop_price": 400}]
        assert store.get("watchlist-groups:live")[0]["symbols"] == ["00700.HK"]
        assert store.get("valuations:live") == {"00700.HK": {"currency": "HKD"}}
        assert store.get("state:live:00700.HK:long:day:regular") == {"last_sent": 1}
        for symbol in ("700.HK", "00700.HK", "000001.SZ", "600519.SH"):
            assert store.bars("live", symbol, "day") == []
        assert store.bars("live", "AAPL.US", "day") == [bar]
        store.put_bars("live", "00700.HK", "day", [bar])
    finally:
        store.close()

    store = Store(tmp_path)
    try:
        assert store.bars("live", "00700.HK", "day") == [bar]
    finally:
        store.close()
