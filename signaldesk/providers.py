from __future__ import annotations

import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from .calendar import bar_end
from .markets import HK, US, market_for, normalize_symbol

PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    "longport": ("longportapp.cn", "longportapp.com"),
    "longbridge": ("longbridge.cn", "longbridge.com"),
}
PLATFORM_DEFAULT_DOMAIN: dict[str, str] = {
    "longport": "longportapp.com",
    "longbridge": "longbridge.com",
}


def _tcp_latency_ms(host: str, port: int = 443, timeout: float = 2.0) -> float | None:
    """测量端到端 TLS 握手延迟（ms），避免本机 TUN/代理 Fake-IP 对纯 TCP ACK 秒回造成误判。"""
    t0 = time.perf_counter()
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            with ctx.wrap_socket(sock, server_hostname=host):
                return (time.perf_counter() - t0) * 1000.0
    except OSError:
        return None


def probe_fastest_broker_domain(
    platform: str = "longport",
    timeout: float = 2.0,
    exclude: str | None = None,
) -> str:
    """并行探测同品牌 .cn / .com 行情网关 TLS 握手延迟，自动选择国内直连更快节点且不跨品牌混发。"""
    key = platform if platform in PLATFORM_DOMAINS else "longport"
    candidates = [d for d in PLATFORM_DOMAINS[key] if d != exclude] or list(PLATFORM_DOMAINS[key])
    if len(candidates) == 1:
        return candidates[0]
    with ThreadPoolExecutor(max_workers=len(candidates)) as pool:
        futures = {
            d: pool.submit(_tcp_latency_ms, f"openapi-quote.{d}", 443, timeout)
            for d in candidates
        }
        latencies = {d: fut.result() for d, fut in futures.items()}
    reachable = [(ms, d) for d, ms in latencies.items() if ms is not None]
    if not reachable:
        return candidates[0] if exclude else PLATFORM_DEFAULT_DOMAIN[key]
    reachable.sort(key=lambda item: (item[0], 0 if item[1].endswith(".cn") else 1))
    return reachable[0][1]


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


def _extract_pre_post(sub) -> dict | None:
    """提取 LongPort PrePostQuote（盘前/盘后/夜盘）子行情，忽略无效零值。"""
    if sub is None:
        return None
    try:
        last = float(sub.last_done)
    except (TypeError, ValueError, AttributeError):
        return None
    if last <= 0:
        return None
    stamp = getattr(sub, "timestamp", None)
    return {
        "last": last,
        "prev_close": float(getattr(sub, "prev_close", 0.0) or 0.0) or None,
        "high": float(getattr(sub, "high", 0.0) or 0.0) or None,
        "low": float(getattr(sub, "low", 0.0) or 0.0) or None,
        "volume": int(getattr(sub, "volume", 0) or 0),
        "turnover": float(getattr(sub, "turnover", 0.0) or 0.0),
        "timestamp": aware(stamp).isoformat() if stamp is not None else None,
    }


def _session_key_from_trade_session(raw_session) -> str:
    text = str(raw_session or "").lower()
    if "overnight" in text:
        return "overnight"
    if "pre" in text:
        return "pre"
    if "post" in text:
        return "post"
    return "regular"


class LongPortFeed:
    """Only read APIs are wrapped. No order, watchlist mutation or cloud alert methods."""

    def __init__(self, credentials: dict, emit, domain: str | None = None):
        import longbridge.openapi as lp

        self.lp, self.emit = lp, emit
        platform = credentials.get("platform", "longport")
        allowed = PLATFORM_DOMAINS.get(platform)
        if allowed is None:
            raise ValueError("未知券商平台")
        if domain is not None:
            if domain not in allowed:
                raise ValueError("网关域名与所选券商平台不匹配")
            selected_domain = domain
        else:
            selected_domain = PLATFORM_DEFAULT_DOMAIN[platform]
        self.platform = platform
        self.domain = selected_domain
        self.renew_at = credentials.get("renew_at")
        if credentials.get("method") == "oauth":
            # The SDK's HTTP signer skips HMAC for a Bearer header and empty secret.
            # Supply the vault-managed token without invoking its plaintext file cache.
            auth = (credentials["client_id"], "", f"Bearer {credentials['access_token']}")
        else:
            auth = tuple(credentials[key].strip() for key in ("app_key", "app_secret", "access_token"))
        config = lp.Config.from_apikey(
            *auth,
            http_url=f"https://openapi.{selected_domain}",
            quote_ws_url=f"wss://openapi-quote.{selected_domain}/v2",
            trade_ws_url=f"wss://openapi-trade.{selected_domain}/v2",
            enable_overnight=True,
            push_candlestick_mode=lp.PushCandlestickMode.Confirmed,
            enable_print_quote_packages=False,
        )
        self.quote_context = lp.QuoteContext(config)
        self.trade_context = lp.TradeContext(config)
        self.symbols = set()
        self.quote_context.set_on_quote(self._on_quote)

    def _on_quote(self, symbol, quote):
        symbol = normalize_symbol(symbol, broker=True)
        session_key = _session_key_from_trade_session(getattr(quote, "trade_session", None))
        stamp = aware(quote.timestamp)
        if session_key != "regular":
            if market_for(symbol) != US:
                return
            # 盘外推送走独立通道，绝不覆盖常规盘主价或触发常规盘计划穿越
            try:
                last = float(quote.last_done)
            except (TypeError, ValueError):
                return
            if last <= 0:
                return
            self.emit(
                {
                    "type": "extended_quote",
                    "symbol": symbol,
                    "session": session_key,
                    "quote": {
                        "last": last,
                        "high": float(getattr(quote, "high", 0.0) or 0.0) or None,
                        "low": float(getattr(quote, "low", 0.0) or 0.0) or None,
                        "volume": int(getattr(quote, "volume", 0) or 0),
                        "turnover": float(getattr(quote, "turnover", 0.0) or 0.0),
                        "timestamp": stamp.isoformat(),
                    },
                }
            )
            return
        self.emit(
            {
                "type": "quote",
                "symbol": symbol,
                "quote": {
                    "last": float(quote.last_done),
                    "open": float(getattr(quote, "open", 0.0) or 0.0) or None,
                    "high": float(getattr(quote, "high", 0.0) or 0.0) or None,
                    "low": float(getattr(quote, "low", 0.0) or 0.0) or None,
                    "volume": int(getattr(quote, "volume", 0) or 0),
                    "turnover": float(getattr(quote, "turnover", 0.0) or 0.0),
                    "timestamp": stamp.isoformat(),
                    "trade_status": str(getattr(quote, "trade_status", "Normal")).split(".")[-1],
                    "session": "regular",
                },
            }
        )

    def history(self, symbol: str, timeframe: str, initial: bool = False) -> list[dict]:
        lp, ctx = self.lp, self.quote_context
        period = lp.Period.Day if timeframe == "day" else lp.Period.Min_15
        # 采用前复权（ForwardAdjust）：最新价与真实市场价保持一致，同时自动消除拆股、合股与除息断崖跳空
        batch = ctx.history_candlesticks_by_offset(
            symbol,
            period,
            lp.AdjustType.ForwardAdjust,
            False,
            1000 if initial else 5,
            None,
            lp.TradeSessions.Intraday if timeframe == "day" or market_for(symbol) != US else lp.TradeSessions.All,
        )
        now = datetime.now(timezone.utc)
        market = market_for(symbol)
        return [normalize_bar(c, timeframe, bar_end(aware(c.timestamp), timeframe, market) <= now) for c in batch]

    def valuations(self, symbols: list[str]) -> dict:
        from .indicators import finite

        idx = self.lp.CalcIndex
        fields = [idx.PeTtmRatio, idx.PbRatio, idx.DividendRatioTtm]
        for extra in ("TurnoverRate", "TotalMarketValue"):
            member = getattr(idx, extra, None)
            if member is not None:
                fields.append(member)
        result = {}
        for group in self._market_batches(symbols):
            currencies = {}
            if market_for(group[0]) == HK:
                try:
                    currencies = {normalize_symbol(s.symbol, broker=True): s.currency
                                  for s in self.quote_context.static_info(group)}
                except Exception:
                    pass
            try:
                batch = self.quote_context.calc_indexes(group, fields)
            except Exception:
                for symbol in group:
                    result[symbol] = {"currency": currencies.get(symbol), "refresh_failed": True}
                continue
            fetched = datetime.now(timezone.utc).isoformat()
            for item in batch:
                symbol = normalize_symbol(item.symbol, broker=True)
                result[symbol] = {
                    "currency": currencies.get(symbol),
                    "pe_ttm": finite(item.pe_ttm_ratio),
                    "pb": finite(item.pb_ratio),
                    "dividend_yield_pct": finite(item.dividend_ratio_ttm),
                    "turnover_rate_pct": finite(getattr(item, "turnover_rate", None)),
                    "market_cap": finite(getattr(item, "total_market_value", None)),
                    "fetched_at": fetched,
                }
        return result

    @staticmethod
    def _market_batches(symbols: list[str]):
        groups: dict[str, list[str]] = {}
        for symbol in symbols:
            groups.setdefault(market_for(symbol).code, []).append(symbol)
        for group in groups.values():
            for start in range(0, len(group), 100):
                yield group[start:start + 100]

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
        for batch in self._market_batches(symbols):
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
                extended = {}
                for sess_key, attr in (
                    ("pre", "pre_market_quote"),
                    ("post", "post_market_quote"),
                    ("overnight", "overnight_quote"),
                ):
                    parsed = _extract_pre_post(getattr(quote, attr, None))
                    if parsed is not None:
                        extended[sess_key] = parsed
                quote_payload = {
                    "last": float(quote.last_done),
                    "prev_close": float(quote.prev_close),
                    "open": float(getattr(quote, "open", 0.0) or 0.0) or None,
                    "high": float(getattr(quote, "high", 0.0) or 0.0) or None,
                    "low": float(getattr(quote, "low", 0.0) or 0.0) or None,
                    "volume": int(getattr(quote, "volume", 0) or 0),
                    "turnover": float(getattr(quote, "turnover", 0.0) or 0.0),
                    "timestamp": aware(quote.timestamp).isoformat(),
                    "trade_status": str(quote.trade_status).split(".")[-1],
                    "session": "regular",
                }
                symbol = normalize_symbol(quote.symbol, broker=True)
                if extended and market_for(symbol) == US:
                    quote_payload["extended"] = extended
                result.append({"symbol": symbol, "quote": quote_payload})
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
                try:
                    symbol = normalize_symbol(raw_symbol, broker=True)
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
                try:
                    symbol = normalize_symbol(pos.symbol, broker=True)
                except ValueError:
                    unsupported.append(pos.symbol)
                    continue
                if float(pos.quantity) < 0:
                    unsupported.append(pos.symbol)
                    continue
                quantity, cost = float(pos.quantity), float(pos.cost_price)
                item = accumulated.setdefault(
                    symbol,
                    {
                        "symbol": symbol,
                        "currency": getattr(pos, "currency", None),
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
            total_cost = item.pop("total_cost")
            item["cost_price"] = total_cost / item["broker_quantity"] if item["broker_quantity"] else None
            if not item["cost_price"] or item["cost_price"] <= 0:
                item["cost_price"] = None
        balances = self.trade_context.account_balance("USD")
        usd = next((b for b in balances if b.currency == "USD"), None)
        net_by_currency = {}
        for currency in {p["currency"] for p in accumulated.values()} - {"USD", None, ""}:
            try:
                balance = next(b for b in self.trade_context.account_balance(currency) if b.currency == currency)
                net_by_currency[currency] = float(balance.net_assets)
            except Exception:
                continue
        return {
            "net_assets_by_currency": net_by_currency,
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
