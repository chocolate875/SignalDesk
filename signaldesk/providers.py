from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .calendar import bar_end, session_for


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


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
        import longport.openapi as lp

        self.lp, self.emit = lp, emit
        config = lp.Config.from_apikey(
            credentials["app_key"],
            credentials["app_secret"],
            credentials["access_token"],
            http_url="https://openapi.longportapp.com",
            quote_ws_url="wss://openapi-quote.longportapp.com/v2",
            trade_ws_url="wss://openapi-trade.longportapp.com/v2",
            enable_overnight=True,
            push_candlestick_mode=lp.PushCandlestickMode.Confirmed,
            enable_print_quote_packages=False,
        )
        self.quote_context = lp.QuoteContext(config)
        self.trade_context = lp.TradeContext(config)
        self.symbols = set()
        self.quote_context.set_on_quote(self._on_quote)
        self.quote_context.set_on_candlestick(self._on_candle)

    def _on_quote(self, symbol, quote):
        stamp = aware(quote.timestamp)
        self.emit(
            {
                "type": "quote",
                "symbol": symbol,
                "quote": {
                    "last": float(quote.last_done),
                    "timestamp": stamp.isoformat(),
                    "trade_status": str(getattr(quote, "trade_status", "Normal")).split(".")[-1],
                    "session": session_for(stamp)["session"],
                },
            }
        )

    def _on_candle(self, symbol, event):
        if not event.is_confirmed:
            return
        timeframe = "day" if event.period == self.lp.Period.Day else "15m"
        self.emit(
            {
                "type": "bar",
                "symbol": symbol,
                "timeframe": timeframe,
                "bar": normalize_bar(event.candlestick, timeframe, True),
            }
        )

    def history(self, symbol: str, timeframe: str, initial: bool = False) -> list[dict]:
        lp, ctx = self.lp, self.quote_context
        period = lp.Period.Day if timeframe == "day" else lp.Period.Min_15
        result = []
        before = None
        for _ in range(4 if initial and timeframe == "15m" else 1):
            batch = ctx.history_candlesticks_by_offset(
                symbol,
                period,
                lp.AdjustType.NoAdjust,
                False,
                1000 if timeframe == "15m" else 320,
                before,
                lp.TradeSessions.Intraday if timeframe == "day" else lp.TradeSessions.All,
            )
            result.extend(
                normalize_bar(
                    c, timeframe, bar_end(aware(c.timestamp), timeframe) <= datetime.now(timezone.utc)
                )
                for c in batch
            )
            if len(batch) < 1000 or timeframe == "day":
                break
            before = min(c.timestamp for c in batch) - timedelta(seconds=1)
        return sorted({b["timestamp"]: b for b in result}.values(), key=lambda b: b["timestamp"])

    def subscribe(self, symbols: list[str]):
        new = set(symbols) - self.symbols
        for symbol in new:
            self.quote_context.subscribe([symbol], [self.lp.SubType.Quote], is_first_push=True)
            self.quote_context.subscribe_candlesticks(
                symbol, self.lp.Period.Min_15, self.lp.TradeSessions.All
            )
            self.quote_context.subscribe_candlesticks(
                symbol, self.lp.Period.Day, self.lp.TradeSessions.Intraday
            )
        self.symbols |= new

    def quotes(self, symbols: list[str]) -> list[dict]:
        if not symbols:
            return []
        result = []
        session = session_for(datetime.now(timezone.utc))["session"]
        for quote in self.quote_context.quote(symbols):
            ext = getattr(
                quote,
                {"pre": "pre_market_quote", "post": "post_market_quote", "overnight": "overnight_quote"}.get(
                    session, "__missing__"
                ),
                None,
            )
            active = ext or quote
            spread = None
            try:
                depth = self.quote_context.depth(quote.symbol)
                bid, ask = float(depth.bids[0].price), float(depth.asks[0].price)
                if ask >= bid > 0:
                    spread = (ask - bid) / ((ask + bid) / 2)
            except Exception:
                pass  # Level-one prices never stand in for unavailable depth.
            result.append(
                {
                    "symbol": quote.symbol,
                    "quote": {
                        "last": float(active.last_done),
                        "prev_close": float(quote.prev_close),
                        "timestamp": aware(active.timestamp).isoformat(),
                        "spread_ratio": spread,
                        "trade_status": str(quote.trade_status).split(".")[-1],
                        "session": session,
                    },
                }
            )
        return result

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
