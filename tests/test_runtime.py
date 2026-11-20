import asyncio
import json
from pathlib import Path

import pytest

from signaldesk.codex_bridge import CodexBridge
from signaldesk.models import Allocation, CodexSettings, QQSettings, utcnow
from signaldesk.notifications import DeliveryResult, NotificationDispatcher
from signaldesk.storage import Store


@pytest.mark.asyncio
async def test_notification_pause_priority_batch_and_demo_boundary(tmp_path):
    class FakeVault:
        def configured(self, service):
            return True

    store = Store(tmp_path)
    dispatcher = NotificationDispatcher(
        store, FakeVault(), QQSettings(enabled=True, app_id="demo-app", target_openid="target")
    )
    sent = []

    async def sender(envelope):
        sent.append(envelope)
        return DeliveryResult("delivered", "mock receipt")

    dispatcher.qq.send = sender
    target = "demo-app:user:target"
    for index, severity in enumerate(["info", "info", "critical"]):
        payload = {
            "event_id": str(index),
            "symbol": "TEST.US",
            "timeframe": "15m",
            "session": "regular",
            "severity": severity,
            "title": "测试",
            "message": "synthetic",
            "score": 75,
            "data_as_of": utcnow().isoformat(),
            "source": "live",
        }
        store.enqueue(str(index), "qq", target, payload)
    dispatcher.delivery_enabled = False
    await dispatcher.tick()
    assert not sent
    dispatcher.delivery_enabled = True
    dispatcher.pause_ordinary = True
    await dispatcher.tick()
    assert len(sent) == 1 and sent[0].severity == "critical"
    dispatcher.pause_ordinary = False
    await dispatcher.tick()
    assert len(sent) == 2 and sent[1].symbol == "MULTI"
    assert all(d["status"] == "delivered" for d in store.deliveries())
    await dispatcher.close()
    store.close()


@pytest.mark.asyncio
async def test_notification_retry_is_bounded_and_survives_restart(tmp_path, monkeypatch):
    class FakeVault:
        def configured(self, service):
            return True

    clock = [1_000_000_000.0]
    monkeypatch.setattr("signaldesk.notifications.time.time", lambda: clock[0])
    store = Store(tmp_path)
    dispatcher = NotificationDispatcher(
        store, FakeVault(), QQSettings(enabled=True, app_id="test", target_openid="target")
    )
    calls = []

    async def limited(envelope):
        calls.append(envelope.event_id)
        return DeliveryResult("limited", "synthetic quota", True, 30)

    dispatcher.qq.send = limited
    store.enqueue(
        "retry",
        "qq",
        "test:user:target",
        {
            "event_id": "retry",
            "symbol": "TEST.US",
            "timeframe": "15m",
            "session": "regular",
            "severity": "critical",
            "title": "测试",
            "message": "合成",
            "data_as_of": utcnow().isoformat(),
        },
    )
    for _ in range(4):
        await dispatcher.tick()
        clock[0] += 60
    assert len(calls) == 3
    assert store.deliveries()[0]["status"] == "limited"
    await dispatcher.close()
    store.close()
    store = Store(tmp_path)
    assert not store.due(clock[0])
    store.close()


@pytest.mark.asyncio
async def test_codex_structured_output_and_environment_are_bounded(tmp_path, monkeypatch):
    store = Store(tmp_path)
    bridge = CodexBridge(store, CodexSettings())
    bridge.executable = "synthetic-codex"
    captured = {}

    class Process:
        returncode = 0

        async def communicate(self, data):
            captured["input"] = data.decode()
            result = {
                "conclusion": "这是合成快照，只能用于技术演示",
                "action": "wait",
                "evidence": ["因子同向"],
                "risks": ["演示数据"],
                "confirmation_conditions": ["等待真实行情"],
                "data_as_of": "2026-10-28T10:00:00Z",
            }
            captured["result_path"].write_text(json.dumps(result), encoding="utf-8")
            return b'{"type":"turn.completed","usage":{"input_tokens":100}}\n', b""

    async def spawn(*args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        captured["result_path"] = Path(args[args.index("-o") + 1])
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setenv("LONGPORT_ACCESS_TOKEN", "CANARY_PRIVATE_TOKEN")
    snapshot = {"symbol": "TEST.US", "technical": {}, "source": "demo"}
    result = await bridge._analyze({"id": "synthetic-job", "snapshot": snapshot})
    assert result.action == "wait"
    assert "CANARY_PRIVATE_TOKEN" not in captured["input"]
    assert "LONGPORT_ACCESS_TOKEN" not in captured["env"]
    assert "--ignore-user-config" in captured["args"]
    assert bridge.process is None
    store.close()


@pytest.mark.asyncio
async def test_codex_timeout_kills_child_without_blocking_monitor(tmp_path, monkeypatch):
    store = Store(tmp_path)
    settings = CodexSettings()
    settings.timeout_seconds = 0.01
    bridge = CodexBridge(store, settings)
    bridge.executable = "synthetic-codex"
    killed = []

    class Process:
        async def communicate(self, data):
            await asyncio.sleep(30)

        def kill(self):
            killed.append(True)

        async def wait(self):
            return -1

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(TimeoutError):
        await bridge._analyze({"id": "timeout-job", "snapshot": {"source": "demo"}})
    assert killed and bridge.process is None
    store.close()


@pytest.mark.asyncio
async def test_automatic_codex_budget_persists_and_demo_does_not_auto_call(tmp_path):
    store = Store(tmp_path)
    bridge = CodexBridge(store, CodexSettings(automatic=True, daily_limit=1))
    bridge.executable = "synthetic-codex"
    stock = {"symbol": "TEST.US", "summaries": {}, "quote": {}}
    assert await bridge.request(stock, "demo", automatic=True) is None
    assert await bridge.request(stock, "live", automatic=True)
    second = CodexBridge(store, CodexSettings(automatic=True, daily_limit=1))
    second.executable = "synthetic-codex"
    assert await second.request({"symbol": "OTHER.US", "summaries": {}}, "live", automatic=True) is None
    store.close()


@pytest.mark.asyncio
async def test_codex_defaults_to_manual_only_and_events_do_not_auto_trigger(tmp_path):
    from signaldesk.service import Monitor

    assert CodexSettings().automatic is False
    store = Store(tmp_path)
    monitor = Monitor(store)
    monitor.settings.mode = "live"
    monitor.settings.codex.automatic = True
    monitor.codex.executable = "synthetic-codex"
    store.set(
        "portfolio:live",
        [Allocation(symbol="NVDA", long_quantity=5, broker_quantity=5).model_dump()],
    )
    event = {
        "id": "evt-manual-check",
        "event_id": "evt-manual-check",
        "source": "live",
        "symbol": "NVDA.US",
        "sleeve": "long",
        "timeframe": "day",
        "session": "regular",
        "severity": "critical",
        "title": "触及计划失效价",
        "message": "复核计划",
        "data_as_of": utcnow().isoformat(),
        "evidence": [],
        "historical": False,
    }
    await monitor.on_events([event])
    assert len(store.deliveries()) == 1
    assert monitor.codex.queue.qsize() == 0
    assert store.analyses() == []
    job_id = await monitor.codex.request(
        monitor.stock(monitor.portfolio("live")[0]), "live", automatic=False
    )
    assert job_id and monitor.codex.queue.qsize() == 1
    await monitor.stop()
