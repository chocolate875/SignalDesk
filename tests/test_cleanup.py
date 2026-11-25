import sqlite3
import sys

from signaldesk.cleanup import clean_data, main
from signaldesk.launcher import claim_instance
from signaldesk.storage import Store


def test_clear_k_lines_preserves_local_settings_and_credentials(tmp_path):
    store = Store(tmp_path)
    store.set("settings", {"mode": "live"})
    store.set("portfolio:live", [{"symbol": "00700.HK", "favorite": True}])
    bar = {"timestamp": "2026-11-25T00:00:00+00:00", "confirmed": True}
    store.put_bars("live", "00700.HK", "day", [bar])
    store.put_bars("macro-live", "SPY.US", "day", [bar])
    store.close()
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    secret = credentials / "longport.encrypted"
    secret.write_bytes(b"fake")

    assert "2 条" in clean_data(tmp_path, cache_only=True)

    with sqlite3.connect(tmp_path / "signaldesk.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM bars").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM kv WHERE key IN ('settings', 'portfolio:live')").fetchone()[0] == 2
    assert secret.read_bytes() == b"fake"


def test_reset_removes_app_data_and_preserves_other_files(tmp_path):
    store = Store(tmp_path)
    store.close()
    for suffix in ("-wal", "-shm"):
        (tmp_path / f"signaldesk.sqlite3{suffix}").touch()
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    for name in ("longport.encrypted", "qq.encrypted", "longbridge_client.encrypted", "qq.tmp", "other.txt"):
        (credentials / name).touch()
    for name in ("codex-exports", "agent-exports"):
        job = tmp_path / name / "job"
        job.mkdir(parents=True)
        (job / "result.json").touch()
    (tmp_path / "notes.txt").touch()

    assert "已重置" in clean_data(tmp_path, cache_only=False)

    assert {path.name for path in tmp_path.iterdir()} == {"instance.lock", "credentials", "notes.txt"}
    assert [path.name for path in credentials.iterdir()] == ["other.txt"]
    assert "已重置" in clean_data(tmp_path, cache_only=False)


def test_cancelling_cleanup_leaves_active_instance_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALDESK_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["cleanup", "all"])
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    store = Store(tmp_path)
    store.close()
    with claim_instance(tmp_path, 8765) as (owner, _):
        main()
        assert not owner.stop_request(tmp_path).exists()
        assert (tmp_path / "signaldesk.sqlite3").is_file()
