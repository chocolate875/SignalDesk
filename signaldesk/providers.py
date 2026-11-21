from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .calendar import bar_end
from .models import Allocation


def aware(value: datetime) -> datetime:
    # Naive SDK timestamps are local time. Aware timestamps keep their original offset.
    return value.astimezone(timezone.utc)


def normalize_bar(candle, timeframe: str, confirmed: bool = True) -> dict:
    stamp = aware(candle.timestamp)
    raw_session = str(getattr(candle, "trade_session", "Normal")).lower()
    session = (
        "overnight"
        if "overnight" in raw_session
        else "pre"
        if "pre" in raw_session
        else "post"
        if "post" in raw_session
        else "regular"
    )
    return {
        "timestamp": stamp.isoformat(),
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
        "volume": int(candle.volume),
        "turnover": float(candle.turnover),
        "session": "regular" if timeframe == "day" else session,
        "confirmed": confirmed,
    }


class LongPortFeed:
    """Only read APIs are wrapped. No order, watchlist mutation or cloud alert methods."""

    def __init__(self, credentials: dict, emit):
        import longbridge.openapi as lp

        self.lp, self.emit = lp, emit
        domain = {"longport": "longportapp.com", "longbridge": "longbridge.com"}[
            credentials.get("platform", "longport")
        ]
        self.renew_at = credentials.get("renew_at")
        if credentials.get("method") == "oauth":
            # The SDK's HTTP signer skips HMAC for a Bearer header and empty secret.
            # Supply the vault-managed token without invoking its plaintext file cache.
            auth = (credentials["client_id"], "", f"Bearer {credentials['access_token']}")
        else:
            auth = tuple(credentials[key].strip() for key in ("app_key", "app_secret", "access_token"))
        config = lp.Config.from_apikey(
            *auth,
            http_url=f"https://openapi.{domain}",
            quote_ws_url=f"wss://openapi-quote.{domain}/v2",
            trade_ws_url=f"wss://openapi-trade.{domain}/v2",
            enable_overnight=False,
            push_candlestick_mode=lp.PushCandlestickMode.Confirmed,
            enable_print_quote_packages=False,
        )
        self.quote_context = lp.QuoteContext(config)
        self.trade_context = lp.TradeContext(config)
        self.symbols = set()
        self.quote_context.set_on_quote(self._on_quote)

    def _on_quote(self, symbol, quote):
        if quote.trade_session != self.lp.TradeSession.Intraday:
            return
        stamp = aware(quote.timestamp)
        self.emit(
            {
                "type": "quote",
                "symbol": symbol,
                "quote": {
                    "last": float(quote.last_done),
                    "timestamp": stamp.isoformat(),
                    "trade_status": str(getattr(quote, "trade_status", "Normal")).split(".")[-1],
                    "session": "regular",
                },
            }
        )

    def history(self, symbol: str, timeframe: str, initial: bool = False) -> list[dict]:
        lp, ctx = self.lp, self.quote_context
        period = lp.Period.Day if timeframe == "day" else lp.Period.Min_15
        batch = ctx.history_candlesticks_by_offset(
            symbol,
            period,
            lp.AdjustType.NoAdjust,
            False,
            1000 if initial else 5,
            None,
            lp.TradeSessions.Intraday if timeframe == "day" else lp.TradeSessions.All,
        )
        now = datetime.now(timezone.utc)
        return [normalize_bar(c, timeframe, bar_end(aware(c.timestamp), timeframe) <= now) for c in batch]

    def valuations(self, symbols: list[str]) -> dict:
        from .indicators import finite

        idx = self.lp.CalcIndex
        result = {}
        for start in range(0, len(symbols), 100):
            batch = self.quote_context.calc_indexes(
                symbols[start : start + 100], [idx.PeTtmRatio, idx.PbRatio, idx.DividendRatioTtm]
            )
            fetched = datetime.now(timezone.utc).isoformat()
            for item in batch:
                result[item.symbol] = {
                    "pe_ttm": finite(item.pe_ttm_ratio),
                    "pb": finite(item.pb_ratio),
                    "dividend_yield_pct": finite(item.dividend_ratio_ttm),
                    "fetched_at": fetched,
                }
        return result

    def subscribe(self, symbols: list[str]):
        new = [symbol for symbol in dict.fromkeys(symbols) if symbol not in self.symbols]
        for symbol in new:
            try:
                self.quote_context.subscribe([symbol], [self.lp.SubType.Quote])
            except Exception:
                continue
            self.symbols.add(symbol)

    def quotes(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        result = []
        for start in range(0, len(symbols), 100):
            batch = symbols[start : start + 100]
            try:
                items = self.quote_context.quote(batch)
            except Exception:
                items = []
                for sym in batch:
                    try:
                        items.extend(self.quote_context.quote([sym]))
                    except Exception:
                        continue
            for quote in items:
                result.append(
                    {
                        "symbol": quote.symbol,
                        "quote": {
                            "last": float(quote.last_done),
                            "prev_close": float(quote.prev_close),
                            "timestamp": aware(quote.timestamp).isoformat(),
                            "trade_status": str(quote.trade_status).split(".")[-1],
                            "session": "regular",
                        },
                    }
                )
        return result

    def watchlist(self) -> dict:
        groups_out = []
        securities_by_symbol: dict[str, dict] = {}
        unsupported: list[str] = []
        unsupported_seen: set[str] = set()
        for group in self.quote_context.watchlist():
            group_id = int(getattr(group, "id", 0) or 0)
            group_name = str(getattr(group, "name", "") or "").strip() or f"分组 {group_id}"
            group_symbols: list[str] = []
            for sec in getattr(group, "securities", None) or []:
                raw_symbol = str(getattr(sec, "symbol", "") or "").strip().upper()
                if not raw_symbol:
                    continue
                if not raw_symbol.endswith(".US"):
                    if raw_symbol not in unsupported_seen:
                        unsupported_seen.add(raw_symbol)
                        unsupported.append(raw_symbol)
                    continue
                try:
                    symbol = Allocation(symbol=raw_symbol).symbol
                except ValueError:
                    if raw_symbol not in unsupported_seen:
                        unsupported_seen.add(raw_symbol)
                        unsupported.append(raw_symbol)
                    continue
                if symbol not in group_symbols:
                    group_symbols.append(symbol)
                entry = securities_by_symbol.setdefault(
                    symbol,
                    {"symbol": symbol, "name": "", "groups": []},
                )
                sec_name = str(getattr(sec, "name", "") or "").strip()
                if sec_name and not entry["name"]:
                    entry["name"] = sec_name
                if group_name not in entry["groups"]:
                    entry["groups"].append(group_name)
            groups_out.append({"id": group_id, "name": group_name, "symbols": group_symbols})
        return {
            "groups": groups_out,
            "securities": list(securities_by_symbol.values()),
            "unsupported": unsupported,
        }

    def account(self) -> dict:
        positions = self.trade_context.stock_positions()
        accumulated = {}
        unsupported = []
        for channel in positions.channels:
            for pos in channel.positions:
                if not pos.symbol.endswith(".US") or float(pos.quantity) < 0:
                    unsupported.append(pos.symbol)
                    continue
                quantity, cost = float(pos.quantity), float(pos.cost_price)
                item = accumulated.setdefault(
                    pos.symbol,
                    {
                        "symbol": pos.symbol,
                        "name": pos.symbol_name,
                        "broker_quantity": 0.0,
                        "available_quantity": 0.0,
                        "total_cost": 0.0,
                    },
                )
                item["broker_quantity"] += quantity
                item["available_quantity"] += float(pos.available_quantity)
                item["total_cost"] += quantity * cost
        for item in accumulated.values():
            item["cost_price"] = (
                item.pop("total_cost") / item["broker_quantity"] if item["broker_quantity"] else None
            )
            if not item["cost_price"] or item["cost_price"] <= 0:
                item["cost_price"] = None
        balances = self.trade_context.account_balance("USD")
        usd = next((b for b in balances if b.currency == "USD"), None)
        return {
            "positions": list(accumulated.values()),
            "net_assets": float(usd.net_assets) if usd else None,
            "cash": float(usd.total_cash) if usd else None,
            "unsupported": unsupported,
        }

    def market_calendar(self):
        today = datetime.now(timezone.utc).date()
        days = self.quote_context.trading_days(
            self.lp.Market.US, today - timedelta(days=5), today + timedelta(days=30)
        )
        sessions = self.quote_context.trading_session()
        return {
            "trade_days": [str(day) for day in days.trading_days],
            "half_trade_days": [str(day) for day in days.half_trading_days],
            "session_metadata_available": bool(sessions),
        }

    def close(self):
        # Dropping native contexts shuts down their SDK-owned WebSocket workers.
        self.quote_context = None
        self.trade_context = None
