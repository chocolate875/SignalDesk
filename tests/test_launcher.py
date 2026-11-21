import socket
import subprocess
import sys
from pathlib import Path

import pytest

from signaldesk import desktop, launcher


def test_start_uses_ready_owners_port_and_stop_waits_for_release(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    with launcher.claim_instance(tmp_path, 9101) as (owner, mark_ready):
        assert launcher.active_instance(tmp_path) == owner
        with launcher.claim_instance(tmp_path, 9102) as duplicate:
            assert duplicate is None
        with pytest.raises(RuntimeError, match="ready"):
            launcher.wait_for_desktop(tmp_path, 9102, False, timeout=0.01)
        assert not opened
        mark_ready()
        launcher.start_desktop(tmp_path, 9102, False)
        assert opened == ["http://127.0.0.1:9101"]
        with pytest.raises(RuntimeError, match="not finished"):
            launcher.stop_desktop(tmp_path, timeout=0.01)
        assert owner.stop_request(tmp_path).exists()
    assert not owner.stop_request(tmp_path).exists()
    launcher.stop_desktop(tmp_path)
    with launcher.claim_instance(tmp_path, 9101) as (restarted, _):
        assert restarted.generation != owner.generation


def test_occupied_port_fails_before_initialising_monitor(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALDESK_DATA_DIR", str(tmp_path))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        monkeypatch.setattr(sys, "argv", ["desktop", "--headless", "--port", str(port)])
        with pytest.raises(SystemExit) as failure:
            desktop.main()
        assert failure.value.code == launcher.PORT_UNAVAILABLE
        assert [path.name for path in tmp_path.iterdir()] == ["instance.lock"]
        launcher.stop_desktop(tmp_path)
        with socket.create_connection(("127.0.0.1", port)):
            pass
    assert launcher.active_instance(tmp_path) is None


def test_headless_stop_shuts_down_server_and_releases_port(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALDESK_DATA_DIR", str(tmp_path))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    project = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "signaldesk.desktop", "--headless", "--port", str(port)], cwd=project,
    )
    try:
        launcher.wait_for_desktop(tmp_path, port, True, child=process)
        assert launcher.already_running(port)
        launcher.stop_desktop(tmp_path)
        assert process.wait(timeout=15) == 0
        assert launcher.active_instance(tmp_path) is None
        assert not launcher.already_running(port)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
