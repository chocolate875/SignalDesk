import json
import os
import sys
from datetime import timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from signaldesk import demo, desktop, startup
from signaldesk.indicators import enrich
from signaldesk.models import Allocation, RuleSettings, utcnow
from signaldesk.replay import load_bars
from signaldesk.service import Monitor
from signaldesk.storage import Store


def test_pythonw_server_initializes_without_console_streams(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    config = desktop.server_config("synthetic:app", 8765)
    assert config.host == "127.0.0.1" and not config.access_log


def test_missing_intraday_bar_resets_signal_warmup():
    bars = [b for b in demo.make_bars("NVDA.US", "15m", utcnow()) if b["session"] == "regular"]
    full = enrich(bars, "15m", utcnow(), RuleSettings())
    assert pd.notna(full.iloc[-1].score)
    missing = bars[:-5] + bars[-4:]
    frame = enrich(missing, "15m", utcnow(), RuleSettings())
    assert pd.isna(frame.iloc[-1].score)


def test_replay_json_defaults_match_csv_and_require_explicit_timezone(tmp_path):
    path = tmp_path / "bars.json"
    record = {
        "timestamp": "2026-10-26T13:30:00Z",
        "open": 10,
        "high": 11,
        "low": 9,
        "close": 10,
        "volume": 100,
    }
    path.write_text(json.dumps([record]), encoding="utf-8")
    bars = load_bars(path, "pre")
    assert bars[0]["confirmed"] and bars[0]["session"] == "pre" and bars[0]["turnover"] == 1000
    record["timestamp"] = "2026-10-26T13:30:00"
    path.write_text(json.dumps([record]), encoding="utf-8")
    with pytest.raises(ValueError, match="ISO8601"):
        load_bars(path, "regular")


@pytest.mark.asyncio
async def test_quote_crossings_reject_halt_invalid_and_out_of_order_data(tmp_path):
    monitor = Monitor(Store(tmp_path))
    monitor.settings.mode = "live"
    monitor.store.set("portfolio:live", [{"symbol": "TEST.US", "watch_only": True, "stop_price": 100}])
    collected = []

    async def capture(events):
        collected.extend(events)

    monitor.on_events = capture
    stamp = utcnow() - timedelta(seconds=10)
    await monitor._quote("TEST.US", {"last": 105, "timestamp": stamp.isoformat()})
    await monitor._quote(
        "TEST.US",
        {"last": 0, "trade_status": "Halted", "timestamp": (stamp + timedelta(seconds=1)).isoformat()},
    )
    monitor.summaries[("live", "TEST.US", "15m", "regular")] = {
        "valid": True,
        "score": 90,
        "state": "strong",
        "risks": [],
    }
    halted = monitor.stock(Allocation(symbol="TEST.US", watch_only=True))
    assert halted["summaries"]["15m:regular"]["score"] is None
    assert monitor.detail_for("TEST.US", "15m", "regular")["summary"]["state"] == "unavailable"
    await monitor._quote(
        "TEST.US",
        {
            "last": float("nan"),
            "trade_status": "Normal",
            "timestamp": (stamp + timedelta(seconds=2)).isoformat(),
        },
    )
    assert not collected and monitor.quotes[("live", "TEST.US")]["last"] is None
    await monitor._quote("TEST.US", {"last": 99, "timestamp": (stamp + timedelta(seconds=3)).isoformat()})
    assert len(collected) == 1 and collected[0]["severity"] == "critical"
    await monitor._quote("TEST.US", {"last": 110, "timestamp": stamp.isoformat()})
    assert monitor.quotes[("live", "TEST.US")]["last"] == 99
    await monitor.notifications.close()
    monitor.store.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows adapter")
def test_startup_toggle_writes_current_user_command_and_can_disable(monkeypatch):
    values = {}

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def query(key, name):
        if name not in values:
            raise FileNotFoundError()
        return values[name], 1

    def delete(key, name):
        if name not in values:
            raise FileNotFoundError()
        del values[name]

    fake = SimpleNamespace(
        HKEY_CURRENT_USER="CURRENT_USER",
        REG_SZ=1,
        OpenKey=lambda *args: Key(),
        CreateKey=lambda *args: Key(),
        QueryValueEx=query,
        SetValueEx=lambda key, name, reserved, kind, value: values.__setitem__(name, value),
        DeleteValue=delete,
    )
    monkeypatch.setitem(sys.modules, "winreg", fake)
    assert not startup.state()["enabled"]
    assert startup.set_enabled(True)["enabled"]
    assert "pythonw.exe" in values["SignalDesk"] and "--background" in values["SignalDesk"]
    assert not startup.set_enabled(False)["enabled"]
    assert not values
