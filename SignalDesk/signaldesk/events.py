from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from .models import RuleSettings
from .storage import Store


class EventEngine:
    def __init__(self, store: Store):
        self.store = store

    def fusion(
        self,
        symbol: str,
        sleeve: str,
        summary: dict,
        rules: RuleSettings,
        source: str,
        initial: bool = False,
        historical: bool = False,
    ) -> dict | None:
        key = f"state:{source}:{symbol}:{sleeve}:{summary['timeframe']}:{summary['session']}"
        previous = self.store.get(key)
        # A bad tick never resets the last valid regime (and cannot re-arm a false notification).
        if not summary["valid"]:
            return None
        state, timestamp = summary["state"], summary["as_of"]
        stamp = datetime.fromisoformat(timestamp).timestamp()
        if previous and stamp <= previous["stamp"]:
            return None
        versioned = {
            "state": state,
            "stamp": stamp,
            "last_sent": previous.get("last_sent", 0) if previous else 0,
        }
        self.store.set(key, versioned)
        if initial or previous is None or previous["state"] == state or state == "neutral":
            return None
        dims = list(summary["dimensions"].values())
        confirmations = sum(v >= 60 if state == "strong" else v <= 40 for v in dims if v is not None)
        if confirmations < 2:
            return None
        # Opportunity gating never suppresses downside risk.
        if state == "strong" and not summary["opportunity_allowed"]:
            return None
        if stamp - versioned["last_sent"] < rules.cooldown_minutes * 60:
            return None
        versioned["last_sent"] = stamp
        self.store.set(key, versioned)
        weak = state == "weak"
        event = self._event(
            source,
            symbol,
            sleeve,
            summary["timeframe"],
            summary["session"],
            timestamp,
            "fusion_weak" if weak else "fusion_strong",
            "warning" if weak else "info",
            "技术评分转弱" if weak else "技术评分转强",
            f"评分 {summary['score']:.1f}，{confirmations} 项因子"
            + ("降至 40 分及以下" if weak else "达到 60 分及以上"),
            summary["score"],
            summary["evidence"],
            historical,
            summary["rule_version"],
        )
        return event if self.store.event(event) else None

    def price(
        self,
        symbol: str,
        sleeve: str,
        last: float,
        level: float,
        kind: str,
        timestamp: str,
        source: str,
        session: str,
        initial: bool = False,
    ) -> dict | None:
        key = f"price:{source}:{symbol}:{sleeve}:{kind}:{level}"
        old = self.store.get(key)
        crossed = last <= level if kind == "stop" else last >= level
        self.store.set(key, {"crossed": crossed, "timestamp": timestamp})
        if initial or old is None or not crossed or old["crossed"]:
            return None
        title = "触及计划失效价" if kind == "stop" else "触及目标观察价"
        event = self._event(
            source,
            symbol,
            sleeve,
            "quote",
            session,
            timestamp,
            f"price_{kind}",
            "critical" if kind == "stop" else "warning",
            title,
            "实时价格已越过预设关键位，请复核；未执行交易",
            None,
            [f"观察价 {level:g}", f"最新价 {last:g}"],
            False,
            "price-1.0.0",
        )
        return event if self.store.event(event) else None

    @staticmethod
    def _event(
        source,
        symbol,
        sleeve,
        timeframe,
        session,
        timestamp,
        kind,
        severity,
        title,
        message,
        score,
        evidence,
        historical,
        version,
    ):
        event_id = str(
            uuid5(
                NAMESPACE_URL,
                f"{source}:{symbol}:{sleeve}:{timeframe}:{session}:{timestamp}:{kind}:{version}",
            )
        )
        return {
            "id": event_id,
            "event_id": event_id,
            "source": source,
            "symbol": symbol,
            "sleeve": sleeve,
            "timeframe": timeframe,
            "session": session,
            "data_as_of": timestamp,
            "kind": kind,
            "created": datetime.fromisoformat(timestamp).timestamp(),
            "severity": severity,
            "title": title,
            "message": message,
            "score": score,
            "evidence": evidence,
            "historical": historical,
            "rule_version": version,
        }
