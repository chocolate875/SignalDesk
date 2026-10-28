from __future__ import annotations

import asyncio
import time
from datetime import datetime

from . import demo
from .calendar import NY, bar_end, calendar, session_for
from .codex_bridge import CodexBridge
from .events import EventEngine
from .indicators import chart_rows, enrich, summarize
from .models import Allocation, Settings, utcnow
from .notifications import NotificationDispatcher
from .providers import LongPortFeed
from .security import Vault
from .storage import Store


class Monitor:
    def __init__(self, store: Store):
        self.store = store
        self.vault = Vault(store.directory)
        self.settings = Settings.model_validate(store.get("settings", {}))
        self.engine = EventEngine(store)
        self.notifications = NotificationDispatcher(store, self.vault, self.settings.qq)
        self.notifications.delivery_enabled = self.settings.mode == "live"
        self.notifications.pause_ordinary = self.settings.pause_ordinary
        self.codex = CodexBridge(store, self.settings.codex)
        self.frames = {}
        self.summaries = {}
        self.quotes = {}
        self.feed = None
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self.tasks = []
        self.status = "starting"
        self.detail = "正在加载本机数据"
        self.last_sync = None
        self.last_probe = 0
        self.reconnect_at = 0
        self.failures = 0
        self.active_mode = self.settings.mode
        self.unsupported = []
        self.loop = None

    def portfolio(self) -> list[Allocation]:
        raw = self.store.get(f"portfolio:{self.settings.mode}")
        if raw is None:
            raw = [a.model_dump() for a in demo.allocations()] if self.settings.mode == "demo" else []
            self.store.set(f"portfolio:{self.settings.mode}", raw)
        return [Allocation.model_validate(a) for a in raw]

    def save_allocation(self, incoming: Allocation):
        current = {a.symbol: a for a in self.portfolio()}
        old = current.get(incoming.symbol)
        actual = old.broker_quantity if old else 0
        if incoming.long_quantity + incoming.short_quantity > actual + 1e-6:
            raise ValueError("分类数量不能超过券商持仓数量；观察股请保持数量为0")
        data = incoming.model_dump()
        data.update(
            broker_quantity=actual,
            available_quantity=old.available_quantity if old else 0,
            cost_price=old.cost_price if old else None,
            watch_only=actual == 0,
        )
        current[incoming.symbol] = Allocation.model_validate(data)
        self.store.set(f"portfolio:{self.settings.mode}", [a.model_dump() for a in current.values()])
        return current[incoming.symbol]

    def update_settings(self, value: Settings):
        self.settings = value
        self.store.set("settings", value.model_dump())
        self.notifications.qq.configure(value.qq)
        self.notifications.delivery_enabled = value.mode == "live"
        self.notifications.pause_ordinary = value.pause_ordinary
        self.codex.settings = value.codex
        self.last_probe = 0

    async def start(self, background: bool = True):
        self.loop = asyncio.get_running_loop()
        if self.settings.mode == "demo":
            await asyncio.to_thread(self.prepare_demo)
        else:
            self.status, self.detail = "unconfigured", "请在本机设置LongPort凭据；不会加载演示持仓到实盘"
            for item in self.portfolio():
                await asyncio.to_thread(self.rebuild, item.symbol, True)
        if background:
            self.tasks = [
                asyncio.create_task(self.run()),
                asyncio.create_task(self.notifications.run()),
                asyncio.create_task(self.codex.run()),
            ]

    def prepare_demo(self):
        now = utcnow()
        for item in self.portfolio():
            if item.symbol not in {d[0] for d in demo.DEMO_NAMES}:
                continue
            for timeframe in ["day", "15m"]:
                bars = demo.make_bars(item.symbol, timeframe, now)
                self.store.put_bars("demo", item.symbol, timeframe, bars)
            self.rebuild(item.symbol, initial=True)
            frame = self.frames[("demo", item.symbol, "15m")]
            regular = frame[frame["session"] == "regular"]
            if not regular.empty:
                row = regular.iloc[-1]
                self.quotes[("demo", item.symbol)] = {
                    "last": float(row["close"]),
                    "prev_close": float(regular.iloc[-2]["close"]),
                    "timestamp": row["timestamp"].isoformat(),
                    "spread_ratio": 0.0005,
                    "trade_status": "normal",
                    "session": "regular",
                }
            # Replay actual factor crossings from synthetic history; no fabricated signal cards.
            key = f"demo-seeded:{item.symbol}:{now.date()}"
            if not self.store.get(key):
                for sleeve in item.sleeves():
                    tf = "day" if sleeve == "long" else "15m"
                    frame = self.frames[("demo", item.symbol, tf)]
                    self.store.set(f"state:demo:{item.symbol}:{sleeve}:{tf}:regular", None)
                    indexes = frame.index[frame["session"] == "regular"][-45:]
                    for ix in indexes:
                        end = bar_end(frame.loc[ix, "timestamp"].to_pydatetime(), tf)
                        summary = summarize(
                            frame.loc[:ix],
                            tf,
                            "regular",
                            end,
                            self.settings.rules,
                            self.quotes.get(("demo", item.symbol)),
                            demo=True,
                        )
                        self.engine.fusion(
                            item.symbol, sleeve, summary, self.settings.rules, "demo", historical=True
                        )
                self.store.set(key, True)
            # Establish current state for future live-like updates, with no historical notifications.
            self.rebuild(item.symbol, initial=True)
        self.status, self.detail = "demo", "合成行情与示例持仓 · 不代表真实市场 · 不自动对外发送"

    def rebuild(self, symbol: str, initial=False, catchup=False) -> list[dict]:
        mode, settings, now = self.settings.mode, self.settings, utcnow()
        quote = self.quotes.get((mode, symbol), {})
        events = []
        allocation = next((a for a in self.portfolio() if a.symbol == symbol), None)
        for timeframe in ["day", "15m"]:
            bars = self.store.bars(mode, symbol, timeframe)
            frame = enrich(bars, timeframe, now, settings.rules)
            self.frames[(mode, symbol, timeframe)] = frame
            sessions = ["regular"] if timeframe == "day" else ["regular", "pre", "post", "overnight"]
            for session in sessions:
                summary = summarize(
                    frame, timeframe, session, now, settings.rules, quote, demo=mode == "demo"
                )
                self.summaries[(mode, symbol, timeframe, session)] = summary
                if allocation is None:
                    continue
                for sleeve in allocation.sleeves():
                    if (sleeve == "long") != (timeframe == "day"):
                        continue
                    historical = bool(
                        catchup
                        and summary.get("as_of")
                        and now.timestamp() - datetime.fromisoformat(summary["as_of"]).timestamp() > 120
                    )
                    event = self.engine.fusion(
                        symbol, sleeve, summary, settings.rules, mode, initial=initial, historical=historical
                    )
                    if event:
                        events.append(event)
        return events

    def stock(self, allocation: Allocation) -> dict:
        mode = self.settings.mode
        quote = self.quotes.get((mode, allocation.symbol), {})
        summaries = {
            f"{tf}:{session}": summary
            for (source, symbol, tf, session), summary in self.summaries.items()
            if source == mode and symbol == allocation.symbol
        }
        market = session_for(utcnow())
        active_session = "regular" if mode == "demo" or market["session"] == "closed" else market["session"]
        primary = "day:regular" if allocation.sleeves() == ["long"] else f"15m:{active_session}"
        summary = summaries.get(primary, {})
        last = quote.get("last")
        net = self.store.get(f"account:{mode}", {}).get("net_assets")
        if mode == "demo":
            net = 50_000
        qty = allocation.broker_quantity
        result = {
            **allocation.model_dump(),
            "sleeves": allocation.sleeves(),
            "reconciled": allocation.reconciled,
            "quote": quote,
            "summaries": summaries,
            "primary_key": primary,
            "primary": summary,
            "weight_percent": (qty * last / net * 100) if last and net else None,
            "pnl_percent": ((last / allocation.cost_price - 1) * 100)
            if last and allocation.cost_price
            else None,
            "distance_to_stop_percent": ((last / allocation.stop_price - 1) * 100)
            if last and allocation.stop_price
            else None,
            "change_percent": ((last / quote["prev_close"] - 1) * 100)
            if last and quote.get("prev_close")
            else None,
        }
        return result

    def stocks(self) -> list[dict]:
        return [self.stock(a) for a in self.portfolio()]

    async def snapshot(self) -> dict:
        stocks = self.stocks()
        scores = [s["primary"]["score"] for s in stocks if s["primary"].get("valid")]
        weights = {
            sleeve: sum(s.get("weight_percent", 0) or 0 for s in stocks if sleeve in s["sleeves"])
            for sleeve in ["long", "short"]
        }
        # Split a dual-sleeve position proportionally, never count it twice.
        weights = {
            sleeve: sum(
                (s["weight_percent"] or 0) * s[f"{sleeve}_quantity"] / s["broker_quantity"]
                for s in stocks
                if s["broker_quantity"] > 0
            )
            for sleeve in ["long", "short"]
        }
        return {
            "mode": self.settings.mode,
            "status": self.status,
            "detail": self.detail,
            "now": utcnow().isoformat(),
            "market": session_for(utcnow()),
            "last_sync": self.last_sync,
            "stocks": stocks,
            "events": self.store.events(self.settings.mode, 70),
            "analyses": [{k: v for k, v in a.items() if k != "snapshot"} for a in self.store.analyses()],
            "channels": {
                "qq": await self.notifications.qq.health(),
                "desktop": await self.notifications.desktop.health(),
                "codex": self.codex.public_status(),
            },
            "summary": {
                "count": len(stocks),
                "strong": sum(s >= 70 for s in scores),
                "weak": sum(s <= 30 for s in scores),
                "average": sum(scores) / len(scores) if scores else None,
                "risk_count": sum(bool(s["primary"].get("risks")) or not s["reconciled"] for s in stocks),
                "sleeve_weights": weights,
            },
            "unsupported": self.unsupported,
        }

    def detail_for(self, symbol: str, timeframe: str, session: str):
        allocation = next((a for a in self.portfolio() if a.symbol == symbol), None)
        if allocation is None:
            raise ValueError("股票不在本机监控列表")
        frame = self.frames.get((self.settings.mode, symbol, timeframe))
        rows = chart_rows(frame, session) if frame is not None else []
        return {
            "stock": self.stock(allocation),
            "rows": rows,
            "summary": self.summaries.get((self.settings.mode, symbol, timeframe, session)),
            "timeframe": timeframe,
            "session": session,
        }

    def emit(self, value: dict):
        def enqueue():
            if not self.queue.full():
                self.queue.put_nowait(value)
            else:
                self.status, self.detail = "degraded", "行情队列溢出，正在等待重同步"
                self.last_probe = 0

        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(enqueue)

    async def on_events(self, events: list[dict]):
        for event in events:
            if event["historical"] or event["source"] != "live":
                continue
            if event["sleeve"] == "long" and event["severity"] == "info":
                continue  # Ordinary long-horizon changes go into the closing digest.
            if self.settings.pause_ordinary and event["severity"] != "critical":
                continue
            self.notifications.enqueue(event, self.settings.desktop_notifications, self.settings.qq.enabled)
            allocation = next((a for a in self.portfolio() if a.symbol == event["symbol"]), None)
            if allocation:
                try:
                    await self.codex.request(
                        self.stock(allocation), "live", automatic=True, event_id=event["id"]
                    )
                except ValueError:
                    pass

    async def _connect(self):
        if not self.vault.configured("longport"):
            self.status, self.detail = "unconfigured", "实盘等待本机LongPort凭据；可先手动添加观察股票"
            return
        self.status, self.detail = "connecting", "正在建立券商只读连接与补齐历史行情"
        credentials = self.vault.load("longport")
        self.feed = await asyncio.to_thread(LongPortFeed, credentials, self.emit)
        await self._sync_account()
        symbols = [a.symbol for a in self.portfolio()]
        self.store.set("broker-calendar", await asyncio.to_thread(self.feed.market_calendar))
        for symbol in symbols:
            for tf in ["day", "15m"]:
                bars = await asyncio.to_thread(self.feed.history, symbol, tf, True)
                self.store.put_bars("live", symbol, tf, bars)
            await asyncio.to_thread(self.rebuild, symbol, True)
        await asyncio.to_thread(self.feed.subscribe, symbols)
        self.status, self.detail = "live", "LongPort只读连接已建立；各股票数据有效性独立检查"
        self.failures = 0
        self.last_probe = 0

    async def _sync_account(self):
        account = await asyncio.to_thread(self.feed.account)
        current = {a.symbol: a.model_dump() for a in self.portfolio()}
        seen = set()
        for incoming in account["positions"]:
            old = current.get(incoming["symbol"], Allocation(symbol=incoming["symbol"]).model_dump())
            current[incoming["symbol"]] = {**old, **incoming, "watch_only": False}
            seen.add(incoming["symbol"])
        for symbol, old in current.items():
            if symbol not in seen:
                old.update(broker_quantity=0, available_quantity=0, watch_only=True)
        self.store.set("portfolio:live", list(current.values()))
        self.store.set("account:live", {key: account[key] for key in ["net_assets", "cash"]})
        self.unsupported = account["unsupported"]
        self.last_sync = utcnow().isoformat()

    async def _poll(self):
        await self._sync_account()
        symbols = [a.symbol for a in self.portfolio()]
        new_symbols = set(symbols) - self.feed.symbols
        for symbol in new_symbols:
            for tf in ["day", "15m"]:
                self.store.put_bars(
                    "live", symbol, tf, await asyncio.to_thread(self.feed.history, symbol, tf, True)
                )
            await asyncio.to_thread(self.rebuild, symbol, True)
        await asyncio.to_thread(self.feed.subscribe, symbols)
        for item in await asyncio.to_thread(self.feed.quotes, symbols):
            await self._quote(item["symbol"], item["quote"])
        # Catch missed confirmed bars after transport gaps; catch-up never alerts as a new entry.
        for symbol in symbols:
            for tf in ["day", "15m"]:
                bars = await asyncio.to_thread(self.feed.history, symbol, tf)
                self.store.put_bars("live", symbol, tf, bars)
            await self.on_events(await asyncio.to_thread(self.rebuild, symbol, False, True))
        self.status, self.detail = "live", "数据同步正常；历史补齐不会作为新机会推送"
        self.failures = 0

    async def _quote(self, symbol: str, quote: dict):
        mode = self.settings.mode
        old = self.quotes.get((mode, symbol), {})
        value = {**old, **quote}
        self.quotes[(mode, symbol)] = value
        try:
            stamp = datetime.fromisoformat(value["timestamp"])
            if not 0 <= (utcnow() - stamp).total_seconds() <= 120:
                return
        except (ValueError, TypeError):
            return
        for allocation in self.portfolio():
            if allocation.symbol != symbol or not allocation.reconciled:
                continue
            for kind in ["stop", "target"]:
                level = getattr(allocation, f"{kind}_price")
                if level is None:
                    continue
                # User-specified price levels belong to the tactical sleeve on dual-sleeve holdings.
                sleeve = "short" if "short" in allocation.sleeves() else allocation.sleeves()[0]
                event = self.engine.price(
                    symbol,
                    sleeve,
                    value["last"],
                    level,
                    kind,
                    value["timestamp"],
                    mode,
                    value.get("session", "regular"),
                )
                if event:
                    await self.on_events([event])

    async def _closing_digest(self):
        if self.settings.mode != "live" or self.settings.pause_ordinary:
            return
        now = utcnow()
        day = now.astimezone(NY).date()
        cal = calendar()
        import pandas as pd

        if not cal.is_session(pd.Timestamp(day)):
            return
        close = cal.session_close(pd.Timestamp(day)).to_pydatetime()
        key = f"closing-digest:{day}"
        if now.timestamp() < close.timestamp() + 600 or self.store.get(key):
            return
        longs = [s for s in self.stocks() if "long" in s["sleeves"]]
        if not longs:
            return
        lines = [
            f"{s['symbol']} {s['summaries'].get('day:regular', {}).get('score', None) or '待确认'}"
            for s in longs
        ]
        event = EventEngine._event(
            "live",
            "PORTFOLIO",
            "long",
            "day",
            "regular",
            close.isoformat(),
            "closing_digest",
            "info",
            "长期仓收盘摘要",
            "；".join(lines)[:350],
            None,
            [],
            False,
            "digest-1.0.0",
        )
        self.store.event(event)
        self.notifications.enqueue(event, self.settings.desktop_notifications, self.settings.qq.enabled)
        self.store.set(key, True)

    async def run(self):
        while True:
            try:
                if self.active_mode != self.settings.mode:
                    if self.feed:
                        self.feed.close()
                        self.feed = None
                    self.active_mode = self.settings.mode
                    while not self.queue.empty():
                        self.queue.get_nowait()
                    self.reconnect_at = 0
                    if self.settings.mode == "demo":
                        await asyncio.to_thread(self.prepare_demo)
                if self.settings.mode == "live":
                    if self.feed is None and time.monotonic() >= self.reconnect_at:
                        self.reconnect_at = time.monotonic() + 30
                        await self._connect()
                    if self.feed and time.monotonic() - self.last_probe > 60:
                        self.last_probe = time.monotonic()
                        await self._poll()
                    for _ in range(min(self.queue.qsize(), 150)):
                        item = self.queue.get_nowait()
                        if item["type"] == "quote":
                            await self._quote(item["symbol"], item["quote"])
                        elif item["type"] == "bar":
                            self.store.put_bars("live", item["symbol"], item["timeframe"], [item["bar"]])
                            await self.on_events(await asyncio.to_thread(self.rebuild, item["symbol"]))
                    await self._closing_digest()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.failures += 1
                self.status = "degraded"
                self.detail = f"券商连接/权限受限（{type(error).__name__}），正在重连；数据缺口保留在看板"
                if self.feed:
                    self.feed.close()
                    self.feed = None
                self.reconnect_at = time.monotonic() + min(120, self.failures * 15)
            await asyncio.sleep(0.5)

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.feed:
            self.feed.close()
        await self.notifications.close()
        self.store.close()
