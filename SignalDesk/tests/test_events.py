from datetime import datetime, timedelta, timezone

from signaldesk.events import EventEngine
from signaldesk.models import RuleSettings
from signaldesk.storage import Store


def summary(state, minute, score=None, **changes):
    stamp = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc) + timedelta(minutes=minute)
    value = {
        "valid": True,
        "state": state,
        "score": score if score is not None else (80 if state == "strong" else 20),
        "timeframe": "15m",
        "session": "regular",
        "as_of": stamp.isoformat(),
        "dimensions": {k: 80 if state == "strong" else 20 for k in ["trend", "momentum", "volume_score"]},
        "opportunity_allowed": True,
        "evidence": ["synthetic evidence"],
        "rule_version": "test",
    }
    return {**value, **changes}


def test_persistent_dedup_cooldown_and_reentry(tmp_path):
    store = Store(tmp_path)
    engine = EventEngine(store)
    rules = RuleSettings()
    assert engine.fusion("TEST.US", "short", summary("neutral", 0), rules, "live") is None
    first = engine.fusion("TEST.US", "short", summary("strong", 15), rules, "live")
    assert first and first["kind"] == "fusion_strong"
    assert engine.fusion("TEST.US", "short", summary("strong", 30), rules, "live") is None
    engine.fusion("TEST.US", "short", summary("neutral", 31), rules, "live")
    assert engine.fusion("TEST.US", "short", summary("strong", 32), rules, "live") is None
    engine.fusion("TEST.US", "short", summary("neutral", 55), rules, "live")
    store.close()
    store = Store(tmp_path)
    assert EventEngine(store).fusion("TEST.US", "short", summary("strong", 60), rules, "live")
    assert len(store.events()) == 2
    store.close()


def test_independent_dimensions_and_risk_not_suppressed(tmp_path):
    store = Store(tmp_path)
    engine = EventEngine(store)
    rules = RuleSettings()
    engine.fusion("TEST.US", "short", summary("neutral", 0), rules, "live")
    one_vote = summary("strong", 15, dimensions={"trend": 99, "momentum": 50, "volume_score": 50})
    assert engine.fusion("TEST.US", "short", one_vote, rules, "live") is None
    engine.fusion("TEST.US", "short", summary("neutral", 30), rules, "live")
    assert (
        engine.fusion("TEST.US", "short", summary("strong", 45, opportunity_allowed=False), rules, "live")
        is None
    )
    assert engine.fusion("TEST.US", "short", summary("weak", 60, opportunity_allowed=False), rules, "live")
    # Data loss does not reset/arm an unchanged regime.
    assert engine.fusion("TEST.US", "short", summary("unavailable", 75, valid=False), rules, "live") is None
    assert engine.fusion("TEST.US", "short", summary("weak", 90), rules, "live") is None
    store.close()


def test_price_crossings_and_source_separation(tmp_path):
    store = Store(tmp_path)
    engine = EventEngine(store)
    now = datetime(2026, 10, 27, 15, tzinfo=timezone.utc)
    assert engine.price("TEST.US", "short", 100, 95, "stop", now.isoformat(), "live", "regular") is None
    event = engine.price(
        "TEST.US", "short", 94, 95, "stop", (now + timedelta(seconds=1)).isoformat(), "live", "regular"
    )
    assert event and event["severity"] == "critical" and event["sleeve"] == "short"
    assert (
        engine.price(
            "TEST.US", "short", 93, 95, "stop", (now + timedelta(seconds=2)).isoformat(), "live", "regular"
        )
        is None
    )
    assert store.events("demo") == []
    store.close()
