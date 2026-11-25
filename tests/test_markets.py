from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from signaldesk.calendar import bar_end, latest_expected_end, session_for
from signaldesk.markets import CN, HK, US, normalize_symbol
from signaldesk.models import Allocation
from signaldesk.providers import LongPortFeed
from signaldesk.service import Monitor
from signaldesk.storage import Store


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        (" aapl ", "AAPL.US"),
        ("brk.b", "BRK.B.US"),
        ("00700.hk", "700.HK"),
        ("600519.sh", "600519.SH"),
        ("000001.sz", "000001.SZ"),
    ],
)
def test_allocation_symbol(raw, canonical):
    assert Allocation(symbol=raw).symbol == canonical
    assert normalize_symbol(canonical, broker=True) == canonical


@pytest.mark.parametrize("raw", ["000001", "AAPL.HK", "600519.SG", "VOD.L", "900901.SH", "200012.SZ"])
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
                assert stock["symbol"] == "700.HK" and stock["weight_percent"] == 2.5
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

    feed.quote_context = SimpleNamespace(
        calc_indexes=indexes,
        static_info=lambda symbols: [SimpleNamespace(symbol="80700.HK", currency="CNY")],
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
    finally:
        store.close()
