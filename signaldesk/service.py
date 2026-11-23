from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime
from threading import RLock

from . import demo
from .broker_oauth import BrokerOAuth, OAuthError
from .calendar import NY, bar_end, calendar, latest_expected_end, session_for
from .codex_bridge import CodexBridge
from .events import EventEngine
from .extended_hours import summarize_extended_hours
from .forecast import compute_forecast
from .indicators import chart_rows, enrich, summarize
from .instruments import classify_instrument, compute_fund_metrics
from .macro import (
    MACRO_BENCHMARK_SYMBOLS,
    compute_macro_regime,
    demo_fred_bundle,
    fetch_fred_bundle,
)
from .models import Allocation, Settings, utcnow
from .notifications import NotificationDispatcher
from .providers import LongPortFeed, probe_fastest_broker_domain
from .research import fetch_curve, research_context
from .security import Vault
from .storage import Store
from .wave_trend import compute_wave_trend


class Monitor:
    def __init__(self, store: Store):
        self.store = store
        self.vault = Vault(store.directory)
        self.oauth = BrokerOAuth(self.vault)
        self.settings = Settings.model_validate(store.get("settings", {}))
        self.engine = EventEngine(store)
        self.notifications = NotificationDispatcher(store, self.vault, self.settings.qq)
        self.notifications.delivery_enabled = self.settings.mode == "live"
        self.notifications.pause_ordinary = self.settings.pause_ordinary
        self.codex = CodexBridge(store, self.settings.codex)
        self.frames = {}
        self.summaries = {}
        self.wave_trends = {}
        self.fund_metrics = {}
        self.forecast_cache = {}
        self.frame_lock = RLock()
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
        self.valuation_retry = 0
        self.history_retry_at = {}
        self.valuations = store.get("valuations:live", {})
        self.curve = store.get("treasury:live", {})
        self.demo_curve = {}
        self.fred = store.get("macro-fred:live", {})
        self.demo_fred = {}
        self.macro_frames = {}
        self.macro_benchmark_retry_at = {}
        self.macro_cache = None
        self.watchlist_groups = store.get("watchlist-groups:live", [])
        self.watchlist_unsupported = []
        self.watchlist_sync_error = ""
        self.last_watchlist_sync = store.get("watchlist-last-sync:live")
        self.broker_domain: str | None = None
        self.failed_domain: str | None = None
        self.quote_resync_needed: bool = False
        self.last_quote_resync: float = 0.0
        self.history_backfill_task: asyncio.Task | None = None

    def portfolio(self, mode: str | None = None) -> list[Allocation]:
        mode = mode or self.settings.mode
        raw = self.store.get(f"portfolio:{mode}")
        if raw is None:
            raw = [a.model_dump() for a in demo.allocations()] if mode == "demo" else []
            self.store.set(f"portfolio:{mode}", raw)
        return [Allocation.model_validate(a) for a in raw]

    def save_allocation(self, incoming: Allocation):
        if (
            incoming.long_stop_price
            and incoming.long_target_price
            and incoming.long_stop_price >= incoming.long_target_price
        ):
            raise ValueError("长期计划失效价应低于目标价")
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
            favorite=(
                incoming.favorite
                if (old is None or "favorite" in incoming.model_fields_set)
                else old.favorite
            ),
            in_watchlist=old.in_watchlist if old else False,
            watchlist_groups=old.watchlist_groups if old else [],
            manual_watch=old.manual_watch if old else (actual == 0),
        )
        current[incoming.symbol] = Allocation.model_validate(data)
        self.store.set(f"portfolio:{self.settings.mode}", [a.model_dump() for a in current.values()])
        return current[incoming.symbol]

    def set_favorite(self, symbol: str, favorite: bool) -> Allocation:
        items = self.portfolio()
        target = None
        for item in items:
            if item.symbol == symbol:
                item.favorite = favorite
                target = item
                break
        if target is None:
            raise ValueError("股票不在当前监控列表")
        self.store.set(f"portfolio:{self.settings.mode}", [a.model_dump() for a in items])
        return target

    def update_settings(self, value: Settings):
        self.settings = value
        self.store.set("settings", value.model_dump())
        self.notifications.qq.configure(value.qq)
        self.notifications.delivery_enabled = value.mode == "live"
        self.notifications.pause_ordinary = value.pause_ordinary
        self.codex.settings = value.codex
        self.last_probe = 0

    def _load_cached_macro_benchmarks(self, mode: str = "live"):
        """从独立 SQLite 分区加载宏观基准 ETF 日线，不触碰用户自选列表。"""
        now = utcnow()
        source = f"macro-{mode}"
        for sym in MACRO_BENCHMARK_SYMBOLS:
            bars = self.store.bars(source, sym, "day")
            if not bars:
                continue
            frame = enrich(bars, "day", now, self.settings.rules)
            with self.frame_lock:
                self.macro_frames[(mode, sym)] = frame
        self.macro_cache = None

    def _seed_quote_from_frame(self, symbol: str, mode: str = "live"):
        """实盘启动在首次券商报价到达前，用本机已确认日线收盘预填参考价与昨收，避免满屏「待更新」。"""
        if (mode, symbol) in self.quotes:
            return
        with self.frame_lock:
            frame = self.frames.get((mode, symbol, "day"))
        if frame is None or frame.empty:
            return
        reg = frame[frame["session"] == "regular"] if "session" in frame.columns else frame
        if reg.empty:
            return
        last_row = reg.iloc[-1]
        try:
            close_last = float(last_row["close"])
            if not math.isfinite(close_last) or close_last <= 0:
                return
            ts = bar_end(last_row["timestamp"].to_pydatetime(), "day").isoformat()
            prev_close = None
            if len(reg) >= 2:
                prev_val = float(reg.iloc[-2]["close"])
                if math.isfinite(prev_val) and prev_val > 0:
                    prev_close = prev_val
        except Exception:
            return
        self.quotes[(mode, symbol)] = {
            "last": close_last,
            "prev_close": prev_close,
            "timestamp": ts,
            "trade_status": "normal",
            "session": "regular",
            "seeded": True,
        }

    async def start(self, background: bool = True):
        self.loop = asyncio.get_running_loop()
        if self.settings.mode == "demo":
            await asyncio.to_thread(self.prepare_demo)
        else:
            self.status, self.detail = "unconfigured", "请在本机设置LongPort凭据；不会加载演示持仓到实盘"
            for item in self.portfolio():
                await asyncio.to_thread(self.rebuild, item.symbol, True)
                self._seed_quote_from_frame(item.symbol, "live")
            await asyncio.to_thread(self._load_cached_macro_benchmarks, "live")
        if background:
            self.tasks = [
                asyncio.create_task(self.run()),
                asyncio.create_task(self.notifications.run()),
                asyncio.create_task(self.codex.run()),
                asyncio.create_task(self.refresh_macro()),
            ]

    def prepare_demo(self):
        now = utcnow()
        end = latest_expected_end(now, "day", "regular")
        self.demo_curve = demo.yield_curve(end)
        self.demo_fred = demo_fred_bundle(now)
        for sym in MACRO_BENCHMARK_SYMBOLS:
            bm_bars = demo.make_benchmark_bars(sym, now)
            frame = enrich(bm_bars, "day", now, self.settings.rules)
            with self.frame_lock:
                self.macro_frames[("demo", sym)] = frame
        self.macro_cache = None
        for item in self.portfolio("demo"):
            if item.symbol not in {d[0] for d in demo.DEMO_NAMES}:
                continue
            bars = demo.make_bars(item.symbol, "day", now)
            self.store.put_bars("demo", item.symbol, "day", bars)
            self.rebuild(item.symbol, initial=True, mode="demo")
            regular = self.frames[("demo", item.symbol, "day")]
            if not regular.empty:
                row = regular.iloc[-1]
                reg_end = bar_end(row["timestamp"].to_pydatetime(), "day")
                reg_close = float(row["close"])
                demo_ext = demo.demo_extended_quote(item.symbol, reg_close, reg_end, now)
                quote_entry = {
                    "last": reg_close,
                    "prev_close": float(regular.iloc[-2]["close"]),
                    "timestamp": reg_end.isoformat(),
                    "spread_ratio": 0.0005,
                    "trade_status": "normal",
                    "session": "regular",
                }
                if demo_ext:
                    quote_entry["extended"] = demo_ext
                self.quotes[("demo", item.symbol)] = quote_entry
            # Replay actual factor crossings from synthetic history; no fabricated signal cards.
            key = f"daily-demo-seeded:{item.symbol}:{now.date()}"
            if not self.store.get(key):
                for sleeve in item.sleeves():
                    if sleeve != "long":
                        continue
                    tf = "day"
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
            self.rebuild(item.symbol, initial=True, mode="demo")
        self.status, self.detail = "demo", "合成行情与示例持仓 · 不代表真实市场 · 不自动对外发送"

    def rebuild(self, symbol: str, initial=False, catchup=False, mode=None) -> list[dict]:
        mode, settings, now = mode or self.settings.mode, self.settings, utcnow()
        quote = self.quotes.get((mode, symbol), {})
        bars = self.store.bars(mode, symbol, "day")
        frame = enrich(bars, "day", now, settings.rules)
        summary = summarize(frame, "day", "regular", now, settings.rules, demo=mode == "demo")
        wave_trend = compute_wave_trend(frame, summary)
        fund_metrics = compute_fund_metrics(frame, summary)
        frame_sig = (id(frame), summary.get("as_of"), summary.get("rule_version"))
        with self.frame_lock:
            self.frames[(mode, symbol, "day")] = frame
            self.summaries[(mode, symbol, "day", "regular")] = summary
            self.wave_trends[(mode, symbol)] = (frame_sig, wave_trend)
            self.fund_metrics[(mode, symbol)] = (frame_sig, fund_metrics)
            self.forecast_cache.pop((mode, symbol), None)
            if symbol in MACRO_BENCHMARK_SYMBOLS:
                self.macro_cache = None
        allocation = next((a for a in self.portfolio(mode) if a.symbol == symbol), None)
        if (
            not allocation
            or not allocation.reconciled
            or "long" not in allocation.sleeves()
            or quote.get("trade_status", "normal").lower()
            not in {"normal", "normaltrade", "normal_trade", ""}
        ):
            return []
        historical = bool(
            catchup
            and summary.get("as_of")
            and now.timestamp() - datetime.fromisoformat(summary["as_of"]).timestamp() > 120
        )
        event = self.engine.fusion(
            symbol, "long", summary, settings.rules, mode, initial=initial, historical=historical
        )
        return [event] if event else []

    def macro_regime(self) -> dict:
        """合成当前模式下的六分项宏观水位与市场大势四象限（带分钟级签名缓存）。"""
        mode = self.settings.mode
        now = utcnow()
        fred = self.demo_fred if mode == "demo" else self.fred
        curve = self.demo_curve if mode == "demo" else self.curve
        bm_frames = {}
        bm_sigs = []
        with self.frame_lock:
            for sym in MACRO_BENCHMARK_SYMBOLS:
                frame = self.frames.get((mode, sym, "day"))
                if frame is None or frame.empty:
                    frame = self.macro_frames.get((mode, sym))
                if frame is not None and not frame.empty:
                    bm_frames[sym] = frame
                    bm_sigs.append((sym, id(frame), len(frame)))
                else:
                    bm_sigs.append((sym, 0, 0))
            cached = self.macro_cache

        ny_minute = now.astimezone(NY).strftime("%Y-%m-%d %H:%M")
        sig = (
            mode,
            ny_minute,
            (fred or {}).get("fetched_at"),
            (fred or {}).get("ok_count"),
            (fred or {}).get("refresh_failed"),
            (curve or {}).get("as_of"),
            (curve or {}).get("three_month"),
            (curve or {}).get("ten_year"),
            (curve or {}).get("refresh_failed"),
            tuple(bm_sigs),
        )
        if cached is not None and cached[0] == sig:
            return cached[1]
        result = compute_macro_regime(fred, curve, bm_frames, now, demo=mode == "demo")
        with self.frame_lock:
            self.macro_cache = (sig, result)
        return result

    def stock(self, allocation: Allocation, macro: dict | None = None) -> dict:
        mode = self.settings.mode
        quote = dict(self.quotes.get((mode, allocation.symbol), {}))
        with self.frame_lock:
            frame = self.frames.get((mode, allocation.symbol, "day"))
            summaries = {
                f"{tf}:{session}": dict(summary)
                for (source, symbol, tf, session), summary in self.summaries.items()
                if source == mode and symbol == allocation.symbol
            }
            cached_wt = self.wave_trends.get((mode, allocation.symbol))
            cached_fm = self.fund_metrics.get((mode, allocation.symbol))
            cached_fc = self.forecast_cache.get((mode, allocation.symbol))
        if str(quote.get("trade_status", "normal")).lower() not in {
            "normal",
            "normaltrade",
            "normal_trade",
            "",
        }:
            for value in summaries.values():
                value.update(
                    valid=False,
                    confirmed_price_available=False,
                    score=None,
                    state="unavailable",
                    opportunity_allowed=False,
                    contributions={},
                    contribution_changes={},
                )
                value["risks"] = ["停牌或交易状态受限"] + [
                    r for r in value.get("risks", []) if r != "停牌或交易状态受限"
                ]
        now = utcnow()
        market = session_for(now)
        expected = latest_expected_end(now, "day", "regular") if mode == "live" else None
        primary = "day:regular"
        day = summaries.get(primary)
        if mode == "live" and day and day.get("confirmed_price_available") and day.get("as_of"):
            if expected and datetime.fromisoformat(day["as_of"]) < expected:
                day.update(
                    valid=False,
                    confirmed_price_available=False,
                    state="unavailable",
                    score=None,
                    opportunity_allowed=False,
                    contributions={},
                    contribution_changes={},
                )
                day["risks"] = ["行情过期：最近应完成K线缺失", *day.get("risks", [])]
        default_summary = {
            "timeframe": "day",
            "session": "regular",
            "valid": False,
            "confirmed_price_available": False,
            "score": None,
            "dimensions": {},
            "indicators": {},
            "risks": ["等待有效日线"],
            "state": "unavailable",
            "as_of": None,
            "rule_version": "",
            "opportunity_allowed": False,
            "evidence": [],
        }
        summary = {**default_summary, **summaries.get(primary, {})}
        summary["risks"] = list(summary.get("risks") or [])
        quote_stale = False
        if mode == "live":
            try:
                stamp = datetime.fromisoformat(quote["timestamp"])
                reference = now if market["session"] == "regular" else expected
                quote_stale = stamp > now or reference is None or (reference - stamp).total_seconds() > 120
            except (ValueError, KeyError, TypeError):
                quote_stale = True
        quote["stale"] = quote_stale
        if quote_stale and "报价过期或尚未确认" not in summary["risks"]:
            summary["risks"] = ["报价过期或尚未确认"] + summary["risks"]
        last = quote.get("last")
        net = self.store.get(f"account:{mode}", {}).get("net_assets")
        if mode == "demo":
            net = 50_000
        qty = allocation.broker_quantity
        stop, target = allocation.long_levels()
        instrument = classify_instrument(allocation.symbol, allocation.name)
        is_fund = bool(instrument.get("is_fund"))
        valuation = self.valuations.get(allocation.symbol, {}) if mode == "live" else {}
        curve = self.curve if mode == "live" else self.demo_curve
        if mode == "demo" and summary.get("as_of") and not is_fund:
            index = next((i for i, d in enumerate(demo.DEMO_NAMES) if d[0] == allocation.symbol), None)
            if index is not None:
                valuation = {
                    "pe_ttm": 19.0 + index * 3,
                    "pb": 3.5 + index,
                    "dividend_yield_pct": index / 3,
                    "fetched_at": summary["as_of"],
                }
        macro_data = macro if macro is not None else self.macro_regime()
        real_rate = macro_data.get("real_rate") or {}
        research = research_context(
            valuation,
            curve,
            now,
            mode == "demo",
            real_ten_year=real_rate.get("ten_year_real"),
            real_rate_fresh=real_rate.get("fresh"),
        )
        close = summary.get("close")
        if not allocation.reconciled:
            review = "核对持仓分类"
        elif "long" not in allocation.sleeves():
            review = "未纳入长期计划"
        elif not summary.get("confirmed_price_available") or close is None:
            review = "等待有效日线"
        elif stop is not None and close <= stop:
            review = "复核计划失效价"
        elif target is not None and close >= target:
            review = "复核计划目标价"
        elif (
            not is_fund
            and research["valuation"]["fresh"]
            and valuation.get("pe_ttm") is not None
            and valuation["pe_ttm"] <= 0
        ):
            review = "复核盈利情况"
        elif not is_fund and research["yield_gap_pp"] is None:
            review = "补齐估值或利率依据"
        else:
            review = "按计划观察" if allocation.watch_only else "例行持仓复核"
        long_plan = {
            "status": review,
            "stop": stop,
            "target": target,
            "basis": "regular_daily_close",
            "close": close,
            "as_of": summary.get("as_of"),
            "watch_only": allocation.watch_only,
            "stop_distance_percent": ((close / stop - 1) * 100) if close and stop else None,
            "target_distance_percent": ((close / target - 1) * 100) if close and target else None,
        }

        frame_sig = (id(frame), summary.get("as_of"), summary.get("rule_version"))
        if cached_wt is not None and cached_wt[0] == frame_sig:
            wave_trend = cached_wt[1]
        else:
            wave_trend = compute_wave_trend(frame, summary)
            with self.frame_lock:
                self.wave_trends[(mode, allocation.symbol)] = (frame_sig, wave_trend)

        if cached_fm is not None and cached_fm[0] == frame_sig:
            fund_metrics = cached_fm[1]
        else:
            fund_metrics = compute_fund_metrics(frame, summary)
            with self.frame_lock:
                self.fund_metrics[(mode, allocation.symbol)] = (frame_sig, fund_metrics)

        forecast_sig = (
            frame_sig,
            summary.get("valid"),
            summary.get("confirmed_price_available"),
            summary.get("score"),
            summary.get("state"),
            tuple(summary.get("risks") or ()),
            close,
            stop,
            target,
            instrument.get("asset_type"),
            instrument.get("is_inverse"),
            research["valuation"].get("fresh"),
            research["valuation"].get("pe_ttm"),
            research["valuation"].get("dividend_yield_pct"),
            research["curve"].get("fresh"),
            research["curve"].get("as_of"),
            research["curve"].get("ten_year"),
            research["curve"].get("ten_change_bp"),
            research.get("yield_gap_pp"),
        )
        if cached_fc is not None and cached_fc[0] == forecast_sig:
            forecast = cached_fc[1]
        else:
            forecast = compute_forecast(
                frame,
                summary,
                research,
                long_plan,
                instrument=instrument,
                fund_metrics=fund_metrics,
            )
            with self.frame_lock:
                self.forecast_cache[(mode, allocation.symbol)] = (forecast_sig, forecast)

        verdict = self._build_verdict(
            allocation,
            summary,
            research,
            long_plan,
            instrument=instrument,
            fund_metrics=fund_metrics,
        )
        extended_hours = summarize_extended_hours(
            quote,
            market,
            long_plan,
            wave_trend,
            forecast,
            now,
            demo=mode == "demo",
        )
        result = {
            **allocation.model_dump(),
            "sleeves": allocation.sleeves(),
            "reconciled": allocation.reconciled,
            "instrument": instrument,
            "fund_metrics": fund_metrics,
            "quote": quote,
            "extended_hours": extended_hours,
            "summaries": summaries,
            "primary_key": primary,
            "primary": summary,
            "research": research,
            "long_plan": long_plan,
            "verdict": verdict,
            "forecast": forecast,
            "wave_trend": wave_trend,
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

    @staticmethod
    def _build_verdict(
        allocation: Allocation,
        summary: dict,
        research: dict,
        long_plan: dict,
        instrument: dict | None = None,
        fund_metrics: dict | None = None,
    ) -> dict:
        close = long_plan.get("close")
        stop = long_plan.get("stop")
        target = long_plan.get("target")
        stop_dist = long_plan.get("stop_distance_percent")
        target_dist = long_plan.get("target_distance_percent")
        confirmed = bool(summary.get("confirmed_price_available")) and close is not None
        valid = bool(summary.get("valid"))
        score = summary.get("score")
        state = summary.get("state", "unavailable")
        risks = list(summary.get("risks") or [])
        indicators = summary.get("indicators") or {}
        val = research.get("valuation") or {}
        pe = val.get("pe_ttm")
        val_fresh = bool(val.get("fresh"))
        ey = research.get("earnings_yield_pct")
        gap = research.get("yield_gap_pp")
        held = allocation.broker_quantity > 0
        watch_only = allocation.watch_only
        in_long = "long" in allocation.sleeves()

        inst = instrument or classify_instrument(allocation.symbol, allocation.name)
        is_fund = bool(inst.get("is_fund"))
        is_leveraged = bool(inst.get("is_leveraged"))
        is_inverse = bool(inst.get("is_inverse"))
        type_label = inst.get("type_label", "个股")
        fm = fund_metrics or {}
        dd_high = fm.get("drawdown_from_high_pct")
        pos_52w = fm.get("range_position_pct")
        hv60 = fm.get("hv60_pct")

        # Plan pillar
        if stop is not None and target is not None and close is not None:
            if close <= stop:
                plan_status, plan_tone = "已破失效价", "danger"
            elif close >= target:
                plan_status, plan_tone = "已达目标价", "warning"
            else:
                plan_status, plan_tone = "区间内运行", "positive"
            plan_detail = (
                f"失效 ${stop:.2f}（{stop_dist:+.1f}%）· 目标 ${target:.2f}（{target_dist:+.1f}%）"
            )
        elif stop is not None:
            if close is not None and close <= stop:
                plan_status, plan_tone = "已破失效价", "danger"
            else:
                plan_status, plan_tone = "已设失效价", "neutral"
            dist = f"（{stop_dist:+.1f}%）" if stop_dist is not None else ""
            plan_detail = f"失效 ${stop:.2f}{dist} · 建议补充目标价"
        elif target is not None:
            if close is not None and close >= target:
                plan_status, plan_tone = "已达目标价", "warning"
            else:
                plan_status, plan_tone = "已设目标价", "neutral"
            dist = f"（{target_dist:+.1f}%）" if target_dist is not None else ""
            plan_detail = f"目标 ${target:.2f}{dist} · 建议补充失效价"
        else:
            plan_status, plan_tone = "未设计划价", "muted"
            plan_detail = "点击「编辑计划」设置失效价与目标价"

        # Second pillar: 个股看估值利率，ETF/基金看回撤分位与波动率
        if is_fund:
            second_label = "杠杆波动" if is_leveraged else "回撤波动"
            if dd_high is not None and pos_52w is not None:
                if is_inverse:
                    val_status, val_tone = f"{type_label}", "warning"
                    vol_part = f"年化波动 {hv60:.1f}%" if hv60 is not None else f"年内分位 {pos_52w:.0f}%"
                    val_detail = f"短线对冲 · {vol_part} · 日度损耗"
                elif is_leveraged:
                    val_status = f"回撤 {dd_high:+.1f}%"
                    val_tone = "warning" if (hv60 is not None and hv60 >= 55) or dd_high <= -25 else "neutral"
                    vol_part = f" · 年化波动 {hv60:.1f}%" if hv60 is not None else ""
                    val_detail = f"{type_label} · 年内分位 {pos_52w:.0f}%{vol_part}"
                else:
                    val_status = f"回撤 {dd_high:+.1f}%"
                    val_tone = (
                        "positive"
                        if 25 <= pos_52w <= 75 and dd_high >= -18
                        else ("warning" if pos_52w >= 92 or dd_high <= -25 else "neutral")
                    )
                    vol_part = f" · 年化波动 {hv60:.1f}%" if hv60 is not None else ""
                    val_detail = f"年内分位 {pos_52w:.0f}%{vol_part}"
            else:
                val_status = type_label
                val_tone = "warning" if is_leveraged else "muted"
                val_detail = "有效日线不足60日，等待补齐区间回撤与波动率"
        else:
            second_label = "估值利率"
            if not val_fresh:
                val_status = "估值待更新"
                val_tone = "muted"
                val_detail = f"最近 PE {pe:.1f}x（超过4天未更新）" if pe is not None else "暂无有效券商估值"
            elif pe is not None and pe <= 0:
                val_status, val_tone = "盈利为负", "danger"
                val_detail = f"PE {pe:.1f}x · 需复核亏损与现金流"
            elif gap is not None and pe is not None and ey is not None:
                val_tone = "positive" if gap >= 1.0 else ("warning" if gap < -1.0 else "neutral")
                val_status = f"利差 {gap:+.2f}pp"
                val_detail = f"PE {pe:.1f}x · 盈利收益率 {ey:.2f}%"
            elif pe is not None:
                val_status, val_tone = f"PE {pe:.1f}x", "neutral"
                val_detail = "等待完整美债利率以计算股债利差"
            else:
                val_status, val_tone = "估值缺失", "muted"
                val_detail = "等待券商更新滚动市盈率"

        # Technical pillar
        if not valid or score is None:
            tech_status, tech_tone = "数据待确认", "muted"
            tech_detail = risks[0] if risks else "日线预热或收盘尚未确认"
        else:
            tech_status = {"strong": "结构偏强", "weak": "结构偏弱", "neutral": "结构中性"}.get(
                state, "待确认"
            )
            tech_tone = (
                "positive"
                if state == "strong" and not risks
                else ("warning" if state == "weak" or risks else "neutral")
            )
            risk_note = f"{len(risks)} 项风险" if risks else "无额外风险"
            tech_detail = f"{score:.1f} 分 · {risk_note}"

        pillars = [
            {"key": "plan", "label": "计划价位", "status": plan_status, "tone": plan_tone, "detail": plan_detail},
            {"key": "valuation", "label": second_label, "status": val_status, "tone": val_tone, "detail": val_detail},
            {"key": "technical", "label": "日线结构", "status": tech_status, "tone": tech_tone, "detail": tech_detail},
        ]

        # Plain-language dimension notes
        ma200 = indicators.get("ma200")
        ema20 = indicators.get("ema20")
        ema50 = indicators.get("ema50")
        price_noun = "净值/价格" if is_fund else "股价"
        if close is not None and ma200 is not None and ema20 is not None and ema50 is not None:
            if close >= ma200 and ema20 >= ema50:
                trend_note = f"收盘高于200日线（${ma200:.2f}），EMA20强于EMA50，中长期趋势完整"
            elif close >= ma200:
                trend_note = f"收盘高于200日线（${ma200:.2f}），但EMA20弱于EMA50，短期偏整理"
            elif ema20 >= ema50:
                trend_note = f"{price_noun}仍在200日线（${ma200:.2f}）下方，EMA20上穿呈修复态势"
            else:
                trend_note = f"{price_noun}位于200日线（${ma200:.2f}）下方且均线空头排列，趋势偏弱"
        else:
            trend_note = "日线样本不足200根，暂无法评估200日长期均线"

        rsi = indicators.get("rsi")
        macd_hist = indicators.get("macd_hist")
        if rsi is not None and macd_hist is not None:
            rsi_zone = (
                "超买警戒区"
                if rsi >= 70
                else "偏强区"
                if rsi >= 55
                else "超卖弱势区"
                if rsi <= 30
                else "偏弱区"
                if rsi <= 45
                else "中性区间"
            )
            macd_desc = "MACD柱为正，多头动能占优" if macd_hist >= 0 else "MACD柱为负，动能偏弱"
            momentum_note = f"RSI14 为 {rsi:.1f}（{rsi_zone}），{macd_desc}"
        else:
            momentum_note = "动量指标窗口尚未就绪"

        rvol = indicators.get("rvol")
        ret1 = indicators.get("return_1")
        if rvol is not None and ret1 is not None:
            vol_desc = (
                "显著放量"
                if rvol >= 1.5
                else "温和放量"
                if rvol >= 1.1
                else "明显缩量"
                if rvol <= 0.7
                else "量能平稳"
            )
            dir_desc = f"收涨 {ret1:+.2%}" if ret1 >= 0 else f"收跌 {ret1:+.2%}"
            volume_note = f"成交量为20日均量的 {rvol:.2f} 倍（{vol_desc}），当日{dir_desc}"
        else:
            volume_note = "成交量基准窗口尚未就绪"

        dimension_notes = {
            "trend": trend_note,
            "momentum": momentum_note,
            "volume_score": volume_note,
        }

        if is_fund:
            parts = [type_label]
            if dd_high is not None:
                parts.append(f"距52周高点 {dd_high:+.1f}%")
            if hv60 is not None:
                parts.append(f"年化波动 {hv60:.1f}%")
            val_brief = "，".join(parts)
        else:
            pe_text = f"PE {pe:.1f}x" if pe is not None else "估值待补"
            gap_text = f"股债利差 {gap:+.2f}pp" if gap is not None else ""
            val_brief = f"{pe_text}，{gap_text}" if gap_text else pe_text

        # Deterministic verdict priority 0..9 (plain-language labels + meaning tooltips)
        if in_long and stop is not None and confirmed and close <= stop:
            action, tone, priority = "跌破止损", "danger", 0
            action_meaning = "最新收盘已跌破您设定的止损/失效价，建议立即复核是否止损或减仓"
            headline = f"收盘价 ${close:.2f} 已跌破计划失效价 ${stop:.2f}（{stop_dist:+.1f}%），需立即复核持有逻辑。"
            next_step = (
                f"核对宏观利率与追踪赛道趋势是否走坏；若后续收盘仍未能收回 ${stop:.2f} 上方，按计划评估止损或减仓。"
                if is_fund
                else f"核对基本面是否恶化；若后续收盘仍未能收回 ${stop:.2f} 上方，按长期计划评估止损或减仓。"
            )
        elif in_long and target is not None and confirmed and close >= target:
            action, tone, priority = "触及目标", "warning", 1
            action_meaning = "最新收盘已达到或超过您设定的目标价，可评估分批止盈或上移目标"
            headline = f"收盘价 ${close:.2f} 已达到计划目标价 ${target:.2f}（{target_dist:+.1f}%），当前 {val_brief}。"
            next_step = "评估是否分批兑现收益；若继续看好趋势延续，可在「编辑计划」上移目标价与保护线。"
        elif not allocation.reconciled:
            action, tone, priority = "仓位待核", "warning", 2
            action_meaning = "券商实际持仓股数与本地分配的长期/其他股数合计不一致"
            headline = f"券商持仓 {allocation.broker_quantity:g} 股与本地长期/其他分配合计不一致，暂不出具仓位判断。"
            next_step = "点击「编辑计划」调整长期底仓股数，使合计等于券商持仓。"
        elif not in_long:
            action, tone, priority = "未入长期", "muted", 9
            action_meaning = "该持仓尚未划入长期底仓计划，仅保留持仓股数核对"
            headline = "该持仓未划入长期底仓计划，仅保留数量核对。"
            next_step = "如需纳入长期跟踪，请在「编辑计划」中为其分配长期数量。"
        elif not is_fund and val_fresh and pe is not None and pe <= 0:
            action, tone, priority = "亏损警示", "danger", 3
            action_meaning = "滚动市盈率 PE ≤ 0，说明公司当前处于亏损或估值异常，暂不建议盲目买入"
            headline = f"滚动市盈率为负（PE {pe:.1f}x），公司当前盈利承压或估值异常，长期安全边际需重新确认。"
            next_step = "复核最新财报与现金流状况，并确认当前失效价保护是否充足。"
        elif not confirmed or not valid or score is None:
            action, tone, priority = "数据不足", "muted", 9
            action_meaning = "已确认日线样本不足 200 根或最新收盘待确认，暂无法给出强弱判断"
            reason = risks[0] if risks else "等待日线历史补齐或常规收盘确认"
            headline = f"有效日线或指标窗口尚未完成（{reason}），暂不给出强弱结论。"
            next_step = "待交易日收盘确认且指标预热完成后，系统将自动刷新技术结构与计划价距离。"
        elif is_inverse and not held:
            action, tone, priority = "对冲观察", "warning", 7
            action_meaning = "反向做空杠杆 ETF 仅适合短期对冲或波段交易，长期持有存在每日再平衡损耗"
            headline = f"{type_label}日线评分 {score:.1f} 分（{val_brief}），仅适合作为短期做空对冲工具，不按长期多头配置评估。"
            next_step = "仅在明确看空对应标的指数或对冲组合回撤时短线使用，并严格设定止盈止损位。"
        elif held and (state == "weak" or len(risks) >= 2):
            action, tone, priority = "转弱警惕", "warning", 4
            action_meaning = "持仓标的当前日线结构走弱或技术风险提示较多，需关注回撤防守"
            risk_brief = "；".join(risks[:2]) if risks else f"日线评分 {score:.1f} 分偏弱"
            headline = f"日线评分 {score:.1f} 分，需关注：{risk_brief}（{val_brief}）。"
            next_step = (
                f"重点盯住失效价 ${stop:.2f}（距离 {stop_dist:+.1f}%），观察量价能否企稳修复。"
                if stop is not None and stop_dist is not None
                else (
                    "高波动基金建议尽快设置止损防守位并控制杠杆仓位。"
                    if is_leveraged
                    else "建议补充计划失效价并观察后续日线能否止跌走强，必要时使用 Codex 手动复核。"
                )
            )
        elif watch_only and state == "strong" and not risks:
            action, tone, priority = "关注买点", "positive", 5
            action_meaning = "观察标的日线趋势偏强且无明显技术风险，可结合参考买点关注入场节奏"
            headline = f"日线评分 {score:.1f} 分（结构偏强），无额外技术风险，当前 {val_brief}。"
            next_step = (
                f"结合趋势通道与资金节奏，对照预设观察价（目标 ${target:.2f}）评估入场或分批定投节奏。"
                if target is not None
                else (
                    "可结合回撤分位与美债利率环境分批关注回踩买点；杠杆类产品须严设止损。"
                    if is_fund
                    else "可结合估值水平设定目标入场或观察价位，或点击生成 Codex 总结作进一步复核。"
                )
            )
        elif held and state == "strong" and not risks:
            action, tone, priority = "趋势向好", "positive", 6
            action_meaning = "持仓标的处于上升趋势且无明显技术风险，可顺势持有跟踪"
            headline = f"日线评分 {score:.1f} 分（结构偏强），趋势与动能健康，当前 {val_brief}。"
            next_step = (
                f"继续按计划持有，上方关注目标价 ${target:.2f}（距当前 {target_dist:+.1f}%）。"
                if target is not None and target_dist is not None
                else (
                    "趋势结构良好，留意回撤分位与美债利率变动；杠杆产品建议动态上移移动止损。"
                    if is_fund
                    else "趋势结构良好，可继续持有并定期检查估值与国债利率变化。"
                )
            )
        elif held:
            action, tone, priority = "持有观察", "neutral", 7
            action_meaning = "持仓标的日线结构中性平稳，继续按既定计划跟踪即可"
            extra = f"存在提示：{risks[0]}" if risks else "结构处于中性区间"
            headline = f"日线评分 {score:.1f} 分，{extra}，当前 {val_brief}。"
            next_step = (
                f"维持计划跟踪：失效价 ${stop:.2f} / 目标价 ${target:.2f}。"
                if stop is not None and target is not None
                else "建议补齐计划失效价与目标价，后续收盘按计划复核即可。"
            )
        else:
            if state == "weak":
                action, tone, priority = "弱势观望", "warning", 8
                action_meaning = "观察标的当前日线走弱或处于空头区，暂不急于介入"
                headline = f"观察标的日线评分 {score:.1f} 分偏弱，暂不急于介入（{val_brief}）。"
                next_step = (
                    "等待指数重新站稳均线且回撤企稳后再评估定投或波段介入节奏。"
                    if is_fund
                    else "等待日线重新站稳均线且评分回升至中性以上后再跟踪。"
                )
            else:
                action, tone, priority = "震荡观望", "neutral", 8
                action_meaning = "观察标的走势中性震荡，等待趋势方向或回踩买点更清晰"
                headline = f"观察标的日线评分 {score:.1f} 分，整体平稳（{val_brief}）。"
                next_step = (
                    "持续跟踪回撤分位、趋势通道与美债利率变化；需要时可手动触发 Codex 总结。"
                    if is_fund
                    else "持续跟踪后续收盘评分变化及估值性价比；需要时可手动触发 Codex 总结。"
                )

        return {
            "action": action,
            "action_meaning": action_meaning,
            "tone": tone,
            "priority": priority,
            "headline": headline,
            "next_step": next_step,
            "pillars": pillars,
            "dimension_notes": dimension_notes,
        }

    def stocks(self, macro: dict | None = None) -> list[dict]:
        macro_data = macro if macro is not None else self.macro_regime()
        return [self.stock(a, macro=macro_data) for a in self.portfolio()]

    async def snapshot(self) -> dict:
        macro = self.macro_regime()
        real_rate = macro.get("real_rate") or {}
        stocks = self.stocks(macro=macro)
        scores = [s["primary"]["score"] for s in stocks if s["primary"].get("valid")]
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
            "rules": self.settings.rules.model_dump(),
            "curve": research_context(
                {},
                self.demo_curve if self.settings.mode == "demo" else self.curve,
                utcnow(),
                self.settings.mode == "demo",
                real_ten_year=real_rate.get("ten_year_real"),
                real_rate_fresh=real_rate.get("fresh"),
            )["curve"],
            "macro": macro,
            "mode": self.settings.mode,
            "status": self.status,
            "detail": self.detail,
            "now": utcnow().isoformat(),
            "market": session_for(utcnow()),
            "last_sync": self.last_sync if self.settings.mode == "live" else None,
            "stocks": stocks,
            "watchlist_groups": (
                demo.watchlist_groups() if self.settings.mode == "demo" else self.watchlist_groups
            ),
            "watchlist_sync": {
                "enabled": self.settings.sync_watchlist,
                "last_sync": self.last_watchlist_sync if self.settings.mode == "live" else None,
                "error": self.watchlist_sync_error if self.settings.mode == "live" else "",
                "unsupported_count": (
                    len(self.watchlist_unsupported) if self.settings.mode == "live" else 0
                ),
                "unsupported": (
                    self.watchlist_unsupported[:20] if self.settings.mode == "live" else []
                ),
            },
            "events": self.store.events(self.settings.mode, 70, sleeve="long"),
            "analyses": [
                {k: v for k, v in a.items() if k != "snapshot"}
                for a in self.store.analyses(source=self.settings.mode)
            ],
            "channels": {
                "qq": await self.notifications.qq.health(),
                "desktop": await self.notifications.desktop.health(),
                "codex": self.codex.public_status(),
            },
            "summary": {
                "count": len(stocks),
                "strong": sum(s["primary"].get("state") == "strong" for s in stocks),
                "weak": sum(s["primary"].get("state") == "weak" for s in stocks),
                "average": sum(scores) / len(scores) if scores else None,
                "risk_count": sum(bool(s["primary"].get("risks")) or not s["reconciled"] for s in stocks),
                "sleeve_weights": weights,
                "buy_rated": sum(
                    (s.get("forecast") or {}).get("rating", {}).get("code") in {"strong_buy", "buy"}
                    for s in stocks
                ),
                "hold_rated": sum(
                    (s.get("forecast") or {}).get("rating", {}).get("code") == "hold"
                    for s in stocks
                ),
                "sell_rated": sum(
                    (s.get("forecast") or {}).get("rating", {}).get("code") in {"reduce", "sell"}
                    for s in stocks
                ),
            },
            "unsupported": self.unsupported if self.settings.mode == "live" else [],
        }

    @staticmethod
    def _forming_daily_row(stock: dict, rows: list[dict], now: datetime) -> dict | None:
        """在美股交易日盘中或收盘确认前，基于实时常规报价生成当日未收盘 K 线（仅用于图表展示，不污染正式指标）。"""
        quote = stock.get("quote") or {}
        if quote.get("seeded"):
            return None
        try:
            last = float(quote.get("last"))
            if not math.isfinite(last) or last <= 0:
                return None
            ts_str = quote.get("timestamp")
            if not isinstance(ts_str, str) or not ts_str:
                return None
            q_dt = datetime.fromisoformat(ts_str)
        except (TypeError, ValueError):
            return None

        q_day = q_dt.astimezone(NY).date()
        if rows:
            try:
                last_row_day = datetime.fromisoformat(rows[-1]["timestamp"]).astimezone(NY).date()
                if q_day <= last_row_day:
                    return None
            except (KeyError, TypeError, ValueError):
                pass
        import pandas as pd

        cal = calendar()
        if not cal.is_session(pd.Timestamp(q_day)):
            return None
        # 当日尚未到开盘时间（例如盘前仅停留在旧常规时间戳）不生成今日常规 K 线
        session_open = cal.session_open(pd.Timestamp(q_day)).to_pydatetime()
        if q_dt < session_open or now < session_open:
            return None

        def _pos(val) -> float | None:
            try:
                f = float(val)
                return f if math.isfinite(f) and f > 0 else None
            except (TypeError, ValueError):
                return None

        o = _pos(quote.get("open")) or last
        h = max(_pos(quote.get("high")) or last, o, last)
        lo = min(_pos(quote.get("low")) or last, o, last)
        vol_raw = quote.get("volume")
        vol = int(vol_raw) if isinstance(vol_raw, (int, float)) and math.isfinite(vol_raw) and vol_raw >= 0 else 0
        turn_raw = quote.get("turnover")
        turn = float(turn_raw) if isinstance(turn_raw, (int, float)) and math.isfinite(turn_raw) and turn_raw >= 0 else 0.0
        prev_close = _pos(quote.get("prev_close")) or (_pos(rows[-1].get("close")) if rows else None)
        ret1 = (last / prev_close - 1.0) if prev_close else None

        return {
            "timestamp": session_open.isoformat(),
            "open": round(o, 4),
            "high": round(h, 4),
            "low": round(lo, 4),
            "close": round(last, 4),
            "volume": vol,
            "turnover": round(turn, 2),
            "return_1": ret1,
            "intraday_forming": True,
        }

    def detail_for(self, symbol: str, timeframe: str, session: str):
        allocation = next((a for a in self.portfolio() if a.symbol == symbol), None)
        if allocation is None:
            raise ValueError("股票不在本机监控列表")
        with self.frame_lock:
            frame = self.frames.get((self.settings.mode, symbol, timeframe))
            stock = self.stock(allocation)
        # Older clients can still open intraday history explicitly; it drives no long-term decisions.
        if timeframe == "15m" and frame is None:
            bars = self.store.bars(self.settings.mode, symbol, timeframe)
            if not bars and self.settings.mode == "demo" and symbol in {d[0] for d in demo.DEMO_NAMES}:
                bars = demo.make_bars(symbol, timeframe, utcnow())
            frame = enrich(bars, timeframe, utcnow(), self.settings.rules)
        rows = chart_rows(frame, session, count=1000) if frame is not None else []
        if timeframe == "day" and session == "regular" and self.settings.mode == "live":
            forming = self._forming_daily_row(stock, rows, utcnow())
            if forming is not None:
                rows = [*rows, forming]
        summary = stock["summaries"].get(f"{timeframe}:{session}")
        if summary is None and timeframe == "15m":
            summary = summarize(
                frame,
                timeframe,
                session,
                utcnow(),
                self.settings.rules,
                stock["quote"],
                demo=self.settings.mode == "demo",
            )
        return {
            "stock": stock,
            "mode": self.settings.mode,
            "rows": rows,
            "summary": summary,
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
        if self.settings.mode != "live":
            return
        for event in events:
            if event["historical"] or event["source"] != "live" or event["sleeve"] != "long":
                continue
            if event["sleeve"] == "long" and event["severity"] == "info":
                continue  # Ordinary long-horizon changes go into the closing digest.
            if self.settings.pause_ordinary and event["severity"] != "critical":
                continue
            allocation = next((a for a in self.portfolio() if a.symbol == event["symbol"]), None)
            if allocation is None or not allocation.reconciled or event.get("sleeve") == "unassigned":
                continue
            self.notifications.enqueue(event, self.settings.desktop_notifications, self.settings.qq.enabled)

    def _ordered_symbols(self, mode: str = "live") -> list[str]:
        ordered = sorted(
            self.portfolio(mode),
            key=lambda item: (item.broker_quantity > 0, item.favorite),
            reverse=True,
        )
        return [item.symbol for item in ordered]

    def _frame_has_recent_daily(self, symbol: str, now: datetime) -> bool:
        """检查本机缓存日线是否已对齐至最近应完成常规交易日且近200日无交易日缺口。"""
        expected = latest_expected_end(now, "day", "regular")
        if expected is None:
            return False
        with self.frame_lock:
            frame = self.frames.get(("live", symbol, "day"))
        if frame is None or frame.empty:
            return False
        reg = frame[frame["session"] == "regular"] if "session" in frame.columns else frame
        if reg.empty:
            return False
        last_end = bar_end(reg["timestamp"].iloc[-1].to_pydatetime(), "day")
        if last_end < expected:
            return False
        dates = set(reg["timestamp"].tail(200).dt.tz_convert(NY).dt.date)
        if not dates:
            return False
        cal_sessions = calendar().sessions_in_range(min(dates), max(dates))
        return all(session.date() in dates for session in cal_sessions)

    async def _create_feed_with_fallback(self, credentials: dict) -> LongPortFeed:
        """优先选择同品牌延迟更低的网关（国内自动优先 .cn），失败时自动回退同品牌备用节点。"""
        platform = credentials.get("platform", "longport")
        primary = await asyncio.to_thread(
            probe_fastest_broker_domain, platform, 1.5, self.failed_domain
        )
        try:
            feed = await asyncio.to_thread(LongPortFeed, credentials, self.emit, primary)
            self.broker_domain = feed.domain
            self.failed_domain = None
            return feed
        except asyncio.CancelledError:
            raise
        except Exception:
            fallback = await asyncio.to_thread(
                probe_fastest_broker_domain, platform, 1.5, primary
            )
            if fallback == primary:
                self.failed_domain = primary
                raise
            feed = await asyncio.to_thread(LongPortFeed, credentials, self.emit, fallback)
            self.broker_domain = feed.domain
            self.failed_domain = None
            return feed

    async def _backfill_missing_history(self, symbols: list[str]):
        """后台低并发补齐缺失或未对齐的历史日线与基准 ETF，绝不阻塞首屏报价和实时推送。"""
        feed = self.feed
        if feed is None or self.settings.mode != "live":
            return
        try:
            cal_meta = await asyncio.to_thread(feed.market_calendar)
            self.store.set("broker-calendar", cal_meta)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

        now = utcnow()
        missing_symbols = [
            sym
            for sym in symbols
            if not self._frame_has_recent_daily(sym, now)
            and time.monotonic() >= self.history_retry_at.get(sym, 0)
        ]
        sem = asyncio.Semaphore(5)

        async def fetch_one(sym: str):
            async with sem:
                if self.feed is not feed or self.settings.mode != "live":
                    return
                with self.frame_lock:
                    frame = self.frames.get(("live", sym, "day"))
                need_initial = frame is None or len(frame) < 200
                try:
                    bars = await asyncio.to_thread(feed.history, sym, "day", need_initial)
                    confirmed = [b for b in bars if b.get("confirmed")]
                    if confirmed:
                        self.store.put_bars("live", sym, "day", confirmed)
                        await asyncio.to_thread(self.rebuild, sym, True, mode="live")
                    if not self._frame_has_recent_daily(sym, utcnow()) and not need_initial:
                        full = await asyncio.to_thread(feed.history, sym, "day", True)
                        full_ok = [b for b in full if b.get("confirmed")]
                        if full_ok:
                            self.store.put_bars("live", sym, "day", full_ok)
                            await asyncio.to_thread(self.rebuild, sym, True, mode="live")
                        self.history_retry_at[sym] = time.monotonic() + 3600
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.history_retry_at[sym] = time.monotonic() + 3600

        if missing_symbols:
            await asyncio.gather(*(fetch_one(sym) for sym in missing_symbols))
        if self.feed is feed and self.settings.mode == "live":
            await self._sync_macro_benchmarks()

    async def _connect(self):
        if not self.vault.configured("longport"):
            self.status, self.detail = "unconfigured", "实盘等待本机LongPort凭据；可先手动添加观察股票"
            return
        self.status, self.detail = "connecting", "正在选择最快券商网关并建立只读连接"
        credentials = await self.oauth.credentials()
        self.feed = await self._create_feed_with_fallback(credentials)
        await self._sync_account()
        symbols = self._ordered_symbols("live")
        # 优先在 1 秒内先批量拿到全部最新报价、昨收与盘外行情，再开启实时推送，避免启动出现「待更新」
        if symbols:
            try:
                for item in await asyncio.to_thread(self.feed.quotes, symbols):
                    await self._quote(item["symbol"], item["quote"])
                self.quote_resync_needed = False
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
        await asyncio.to_thread(self.feed.subscribe, symbols)
        # 若有新标的或估值过期，顺手完成一次批量估值刷新
        missing_val = any(s not in self.valuations for s in symbols)
        if symbols and (missing_val or time.monotonic() >= self.valuation_retry):
            try:
                valuations = await asyncio.to_thread(self.feed.valuations, symbols)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.valuation_retry = time.monotonic() + 900
            else:
                self.valuations = valuations
                self.store.set("valuations:live", valuations)
                self.valuation_retry = time.monotonic() + 3600
        if self.settings.mode != "live":
            return
        node_note = f"（{self.broker_domain}）" if self.broker_domain else ""
        self.status, self.detail = "live", f"LongPort只读连接已建立{node_note}；各股票数据有效性独立检查"
        self.failures = 0
        self.last_probe = time.monotonic()
        if self.history_backfill_task and not self.history_backfill_task.done():
            self.history_backfill_task.cancel()
        self.history_backfill_task = asyncio.create_task(self._backfill_missing_history(symbols))

    async def _sync_macro_benchmarks(self):
        """只读拉取全市场基准 ETF（SPY/QQQ/RSP/IWM/HYG/IEF）日线到独立缓存分区，不污染用户自选列表。"""
        if self.settings.mode != "live" or self.feed is None:
            return
        now_mono = time.monotonic()
        now = utcnow()
        updated = False
        for sym in MACRO_BENCHMARK_SYMBOLS:
            with self.frame_lock:
                user_frame = self.frames.get(("live", sym, "day"))
                macro_frame = self.macro_frames.get(("live", sym))
            if user_frame is not None and len(user_frame) >= 220:
                continue
            if now_mono < self.macro_benchmark_retry_at.get(sym, 0.0):
                continue
            initial = macro_frame is None or len(macro_frame) < 220
            try:
                bars = await asyncio.to_thread(self.feed.history, sym, "day", initial)
                confirmed = [b for b in bars if b.get("confirmed")]
                if confirmed:
                    self.store.put_bars("macro-live", sym, "day", confirmed)
                    all_bars = self.store.bars("macro-live", sym, "day")
                    frame = await asyncio.to_thread(enrich, all_bars, "day", now, self.settings.rules)
                    with self.frame_lock:
                        self.macro_frames[("live", sym)] = frame
                    updated = True
                self.macro_benchmark_retry_at[sym] = time.monotonic() + 3600
            except asyncio.CancelledError:
                raise
            except Exception:
                self.macro_benchmark_retry_at[sym] = time.monotonic() + 1800
                continue
        if updated:
            with self.frame_lock:
                self.macro_cache = None

    async def refresh_macro(self):
        curve_retry = 0.0
        fred_retry = 0.0
        while True:
            if self.settings.mode == "live":
                now_mono = time.monotonic()
                if now_mono >= curve_retry:
                    try:
                        curve = await fetch_curve(utcnow())
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.curve = {**self.curve, "refresh_failed": True}
                        curve_retry = time.monotonic() + 900
                    else:
                        self.curve = curve
                        self.store.set("treasury:live", curve)
                        with self.frame_lock:
                            self.macro_cache = None
                        curve_retry = time.monotonic() + 21600
                if time.monotonic() >= fred_retry:
                    try:
                        fred = await fetch_fred_bundle(utcnow(), self.fred)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        self.fred = {**self.fred, "refresh_failed": True}
                        fred_retry = time.monotonic() + 900
                    else:
                        self.fred = fred
                        self.store.set("macro-fred:live", fred)
                        with self.frame_lock:
                            self.macro_cache = None
                        fred_retry = time.monotonic() + (900 if fred.get("refresh_failed") else 21600)
            await asyncio.sleep(15)

    async def _sync_account(self):
        account = await asyncio.to_thread(self.feed.account)
        current = {a.symbol: a.model_dump() for a in self.portfolio("live")}
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
        await self._sync_watchlist()

    async def _sync_watchlist(self, force: bool = False):
        if (
            (not force and not self.settings.sync_watchlist)
            or self.feed is None
            or not hasattr(self.feed, "watchlist")
        ):
            return
        try:
            payload = await asyncio.to_thread(self.feed.watchlist)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.watchlist_sync_error = f"自选同步失败（{type(error).__name__}）"
            return
        current = {a.symbol: a.model_dump() for a in self.portfolio("live")}
        seen = set()
        for sec in payload.get("securities", []):
            sym = sec["symbol"]
            seen.add(sym)
            groups = list(sec.get("groups", []))
            if sym in current:
                old = current[sym]
                current[sym] = {
                    **old,
                    "name": old.get("name") or sec.get("name", ""),
                    "in_watchlist": True,
                    "watchlist_groups": groups,
                }
            else:
                current[sym] = Allocation(
                    symbol=sym,
                    name=sec.get("name", ""),
                    watch_only=True,
                    watch_sleeve="long",
                    in_watchlist=True,
                    watchlist_groups=groups,
                    manual_watch=False,
                ).model_dump()
        cleaned = {}
        for sym, item in current.items():
            if sym not in seen:
                item["in_watchlist"] = False
                item["watchlist_groups"] = []
                if (
                    item.get("broker_quantity", 0) == 0
                    and not item.get("manual_watch")
                    and not item.get("favorite")
                    and item.get("long_stop_price") is None
                    and item.get("long_target_price") is None
                ):
                    continue
            cleaned[sym] = item
        groups = [g for g in payload.get("groups", []) if g.get("symbols")]
        self.store.set("portfolio:live", list(cleaned.values()))
        self.watchlist_groups = groups
        self.watchlist_unsupported = list(payload.get("unsupported", []))
        self.watchlist_sync_error = ""
        self.last_watchlist_sync = utcnow().isoformat()
        self.store.set("watchlist-groups:live", self.watchlist_groups)
        self.store.set("watchlist-last-sync:live", self.last_watchlist_sync)

    async def sync_watchlist_now(self) -> dict:
        if self.settings.mode == "demo":
            groups = demo.watchlist_groups()
            watchlist_count = sum(1 for a in self.portfolio("demo") if a.in_watchlist)
            return {
                "ok": True,
                "mode": "demo",
                "groups_count": len(groups),
                "watchlist_count": watchlist_count,
                "unsupported_count": 0,
                "last_sync": None,
                "message": "演示模式已载入示例自选分组；切换实盘后将自动同步您的 LongPort 账号自选股单",
            }
        if self.feed is None:
            self.reconnect_at = 0
            self.last_probe = 0
            return {
                "ok": False,
                "mode": "live",
                "message": "尚未连接到 LongPort，请先在设置中配置凭据并切换为实盘",
            }
        await self._sync_account()
        if not self.settings.sync_watchlist:
            await self._sync_watchlist(force=True)
        if self.watchlist_sync_error:
            return {
                "ok": False,
                "mode": "live",
                "message": self.watchlist_sync_error,
                "last_sync": self.last_watchlist_sync,
            }
        symbols = self._ordered_symbols("live")
        new_symbols = set(symbols) - self.feed.symbols
        for symbol in symbols:
            if symbol not in new_symbols or time.monotonic() < self.history_retry_at.get(symbol, 0):
                continue
            try:
                bars = await asyncio.to_thread(self.feed.history, symbol, "day", True)
                self.store.put_bars("live", symbol, "day", bars)
                await asyncio.to_thread(self.rebuild, symbol, True, mode="live")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.history_retry_at[symbol] = time.monotonic() + 3600
                continue
        await asyncio.to_thread(self.feed.subscribe, symbols)
        if symbols:
            try:
                for item in await asyncio.to_thread(self.feed.quotes, symbols):
                    await self._quote(item["symbol"], item["quote"])
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            if new_symbols or time.monotonic() >= self.valuation_retry:
                try:
                    valuations = await asyncio.to_thread(self.feed.valuations, symbols)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.valuations = {
                        s: {**self.valuations.get(s, {}), "refresh_failed": True} for s in symbols
                    }
                    self.valuation_retry = time.monotonic() + 900
                else:
                    self.valuations = valuations
                    self.store.set("valuations:live", valuations)
                    self.valuation_retry = time.monotonic() + 3600
        watchlist_count = sum(1 for a in self.portfolio("live") if a.in_watchlist)
        unsupported_count = len(self.watchlist_unsupported)
        self.last_probe = time.monotonic()
        msg = f"已同步 {len(self.watchlist_groups)} 个自选分组，共 {watchlist_count} 只美股"
        if unsupported_count:
            msg += f"（已忽略 {unsupported_count} 只非美股或无效代码）"
        return {
            "ok": True,
            "mode": "live",
            "groups_count": len(self.watchlist_groups),
            "watchlist_count": watchlist_count,
            "unsupported_count": unsupported_count,
            "last_sync": self.last_watchlist_sync,
            "message": msg,
        }

    async def _poll(self, skip_synced_daily: bool = False):
        await self._sync_account()
        symbols = self._ordered_symbols("live")
        new_symbols = set(symbols) - self.feed.symbols
        for symbol in symbols:
            if symbol not in new_symbols or time.monotonic() < self.history_retry_at.get(symbol, 0):
                continue
            with self.frame_lock:
                cached_frame = self.frames.get(("live", symbol, "day"))
            if cached_frame is not None and not cached_frame.empty:
                continue
            try:
                self.store.put_bars(
                    "live", symbol, "day", await asyncio.to_thread(self.feed.history, symbol, "day", True)
                )
                await asyncio.to_thread(self.rebuild, symbol, True, mode="live")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.history_retry_at[symbol] = time.monotonic() + 3600
                continue
        await asyncio.to_thread(self.feed.subscribe, symbols)
        for item in await asyncio.to_thread(self.feed.quotes, symbols):
            await self._quote(item["symbol"], item["quote"])
        self.quote_resync_needed = False
        if symbols and (new_symbols or time.monotonic() >= self.valuation_retry):
            try:
                valuations = await asyncio.to_thread(self.feed.valuations, symbols)
            except Exception:
                self.valuations = {s: {**self.valuations.get(s, {}), "refresh_failed": True} for s in symbols}
                self.valuation_retry = time.monotonic() + 900
            else:
                self.valuations = valuations
                self.store.set("valuations:live", valuations)
                self.valuation_retry = time.monotonic() + 3600
        now = utcnow()
        daily_targets = [
            symbol
            for symbol in symbols
            if not (skip_synced_daily and self._frame_has_recent_daily(symbol, now))
        ]
        if daily_targets:
            sem = asyncio.Semaphore(5)

            async def poll_one(sym: str):
                async with sem:
                    try:
                        await self._poll_daily(sym)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        return

            await asyncio.gather(*(poll_one(sym) for sym in daily_targets))
        await self._sync_macro_benchmarks()
        if self.settings.mode != "live":
            return
        node_note = f"（{self.broker_domain}）" if self.broker_domain else ""
        self.status, self.detail = "live", f"数据同步正常{node_note}；历史补齐不会作为新机会推送"
        self.failures = 0

    async def _poll_daily(self, symbol: str):
        batch = await asyncio.to_thread(self.feed.history, symbol, "day")
        confirmed = [b for b in batch if b["confirmed"]]
        if not confirmed:
            return
        # The transport can survive a sleeping PC while its five-bar history window moves on.
        with self.frame_lock:
            frame = self.frames.get(("live", symbol, "day"))
        cached = set()
        if frame is not None and not frame.empty:
            cached = set(frame["timestamp"].tail(200).dt.tz_convert(NY).dt.date)
        observed = cached | {datetime.fromisoformat(b["timestamp"]).astimezone(NY).date() for b in confirmed}
        expected = calendar().sessions_in_range(min(observed), max(observed))
        missing = not cached or any(session.date() not in observed for session in expected)
        if missing and time.monotonic() >= self.history_retry_at.get(symbol, 0):
            history = await asyncio.to_thread(self.feed.history, symbol, "day", True)
            confirmed.extend(b for b in history if b["confirmed"])
            self.history_retry_at[symbol] = time.monotonic() + 3600
        if self.store.put_bars("live", symbol, "day", confirmed):
            events = await asyncio.to_thread(self.rebuild, symbol, initial=missing, catchup=True, mode="live")
            await self.on_events(events)

    @staticmethod
    def _merge_extended_maps(old_ext: dict | None, new_ext: dict | None) -> dict:
        """按盘外分段（overnight/pre/post）合并报价，拒绝乱序旧时间戳回退。"""
        merged: dict[str, dict] = {
            k: dict(v) for k, v in (old_ext or {}).items() if isinstance(v, dict)
        }
        for key, incoming in (new_ext or {}).items():
            if not isinstance(incoming, dict):
                continue
            prev = merged.get(key)
            if prev and prev.get("timestamp") and incoming.get("timestamp"):
                try:
                    if datetime.fromisoformat(incoming["timestamp"]) < datetime.fromisoformat(prev["timestamp"]):
                        continue
                except ValueError:
                    pass
            base = dict(prev) if prev else {}
            for field, val in incoming.items():
                if val is not None:
                    base[field] = val
            merged[key] = base
        return merged

    async def _extended_quote(self, symbol: str, session_key: str, ext_quote: dict):
        """接收夜盘/盘前/盘后实时推送，仅更新独立 extended 字段，绝不修改常规主价或触发常规盘计划价穿越。"""
        mode = "live"
        if self.settings.mode != mode or session_key not in {"overnight", "pre", "post"}:
            return
        try:
            last = float(ext_quote.get("last"))
            if not math.isfinite(last) or last <= 0:
                return
        except (TypeError, ValueError):
            return
        old = dict(self.quotes.get((mode, symbol), {}))
        cleaned = dict(ext_quote)
        cleaned["last"] = last
        if cleaned.get("prev_close") is None and old.get("last"):
            cleaned["prev_close"] = old["last"]
        old["extended"] = self._merge_extended_maps(old.get("extended"), {session_key: cleaned})
        self.quotes[(mode, symbol)] = old

    def _fallback_prev_close(self, mode: str, symbol: str, trade_day) -> float | None:
        """跨交易日实时推送缺少 prev_close 时，从本机已确认常规日线回退取上一交易日收盘。"""
        with self.frame_lock:
            frame = self.frames.get((mode, symbol, "day"))
        if frame is None or frame.empty:
            return None
        reg = frame[frame["session"] == "regular"] if "session" in frame.columns else frame
        if reg.empty:
            return None
        try:
            dates = reg["timestamp"].dt.tz_convert(NY).dt.date
            prior = reg[dates < trade_day]
            if prior.empty:
                return None
            val = float(prior.iloc[-1]["close"])
            return val if math.isfinite(val) and val > 0 else None
        except Exception:
            return None

    async def _quote(self, symbol: str, quote: dict):
        mode = "live"
        if self.settings.mode != mode:
            return
        old = self.quotes.get((mode, symbol), {})
        merged_ext = self._merge_extended_maps(old.get("extended"), quote.get("extended"))
        value = {**old, **quote}
        if not quote.get("seeded"):
            value.pop("seeded", None)
        if merged_ext:
            value["extended"] = merged_ext
        try:
            last = float(value.get("last"))
            if not math.isfinite(last) or last <= 0:
                last = None
        except (ValueError, TypeError):
            last = None
        value["last"] = last
        try:
            stamp = datetime.fromisoformat(quote["timestamp"])
            if old.get("timestamp"):
                previous = datetime.fromisoformat(old["timestamp"])
                if stamp < previous:
                    # 常规主价不回退，但若有更新的盘外行情仍可保留
                    if merged_ext and merged_ext != old.get("extended"):
                        self.quotes[(mode, symbol)] = {**old, "extended": merged_ext}
                    return  # Late delivery must not rewind price crossing state or the displayed quote.
                if stamp.astimezone(NY).date() != previous.astimezone(NY).date():
                    # 跨交易日时清理上一交易日的盘中 OHLCV，避免旧日开高低混入新一日实时 K 线
                    for k in ("open", "high", "low", "volume", "turnover"):
                        if quote.get(k) is None:
                            value.pop(k, None)
                    if "prev_close" not in quote:
                        fallback = self._fallback_prev_close(mode, symbol, stamp.astimezone(NY).date())
                        if fallback is not None:
                            value["prev_close"] = fallback
                        else:
                            value.pop("prev_close", None)
                        self.quote_resync_needed = True
                else:
                    # 同交易日内合并盘中 OHLCV：保留已有开盘价，高低价与成交量不因缺失字段回退
                    if value.get("open") is None and old.get("open") is not None:
                        value["open"] = old["open"]
                    for k, fn in (("high", max), ("low", min)):
                        cand = [x for x in (old.get(k), quote.get(k), last) if isinstance(x, (int, float)) and math.isfinite(x) and x > 0]
                        if cand:
                            value[k] = fn(cand)
                    for k in ("volume", "turnover"):
                        cand = [x for x in (old.get(k), quote.get(k)) if isinstance(x, (int, float)) and math.isfinite(x) and x >= 0]
                        if cand:
                            value[k] = max(cand)
            elif "prev_close" not in quote and value.get("prev_close") is None:
                fallback = self._fallback_prev_close(mode, symbol, stamp.astimezone(NY).date())
                if fallback is not None:
                    value["prev_close"] = fallback
                self.quote_resync_needed = True
            fresh = 0 <= (utcnow() - stamp).total_seconds() <= 120
        except (ValueError, TypeError, KeyError):
            fresh = False
        self.quotes[(mode, symbol)] = value
        if not fresh or last is None or str(value.get("trade_status", "normal")).lower() != "normal":
            return
        for allocation in self.portfolio():
            if allocation.symbol != symbol or not allocation.reconciled or "long" not in allocation.sleeves():
                continue
            for kind, level in zip(("stop", "target"), allocation.long_levels()):
                if level is None:
                    continue
                event = self.engine.price(
                    symbol,
                    "long",
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
        lines = [f"{s['symbol']} {s['long_plan']['status']}" for s in longs]
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
                    if self.feed and self.feed.renew_at and time.time() >= self.feed.renew_at:
                        credentials = await self.oauth.credentials()
                        fresh = await self._create_feed_with_fallback(credentials)
                        self.feed.close()
                        self.feed = fresh
                        await asyncio.to_thread(fresh.subscribe, self._ordered_symbols("live"))
                    if self.feed is None and time.monotonic() >= self.reconnect_at:
                        self.reconnect_at = time.monotonic() + 30
                        await self._connect()
                    for _ in range(min(self.queue.qsize(), 200)):
                        item = self.queue.get_nowait()
                        if item["type"] == "quote":
                            await self._quote(item["symbol"], item["quote"])
                        elif item["type"] == "extended_quote":
                            await self._extended_quote(
                                item["symbol"], item["session"], item["quote"]
                            )
                    if (
                        self.feed
                        and self.quote_resync_needed
                        and time.monotonic() - self.last_quote_resync >= 5.0
                    ):
                        self.last_quote_resync = time.monotonic()
                        symbols = self._ordered_symbols("live")
                        if symbols:
                            for item in await asyncio.to_thread(self.feed.quotes, symbols):
                                await self._quote(item["symbol"], item["quote"])
                        self.quote_resync_needed = False
                    if self.feed and time.monotonic() - self.last_probe > 60:
                        self.last_probe = time.monotonic()
                        await self._poll(skip_synced_daily=True)
                    await self._closing_digest()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.failures += 1
                self.status = "degraded"
                if self.broker_domain:
                    self.failed_domain = self.broker_domain
                code = getattr(error, "code", None)
                if isinstance(error, OAuthError):
                    self.detail = str(error)
                elif code == 401004:
                    self.detail = "长桥认证失败（401004），请重新登录或核对 API Key 签发网站"
                elif code == 403308:
                    self.detail = "长桥授权缺少所需权限（403308），请核对账户读取及自选股授权"
                elif isinstance(code, int):
                    self.detail = f"长桥请求失败（错误码 {code}），正在重试"
                elif isinstance(error, (TypeError, AttributeError, ValueError)):
                    self.detail = f"本机数据处理出错（{type(error).__name__}），正在重试"
                else:
                    self.detail = f"数据同步失败（{type(error).__name__}），正在重试"
                if self.feed:
                    self.feed.close()
                    self.feed = None
                self.reconnect_at = time.monotonic() + min(120, self.failures * 15)
            await asyncio.sleep(0.25)

    async def stop(self):
        if self.history_backfill_task and not self.history_backfill_task.done():
            self.history_backfill_task.cancel()
            await asyncio.gather(self.history_backfill_task, return_exceptions=True)
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.feed:
            self.feed.close()
        await self.notifications.close()
        self.store.close()
