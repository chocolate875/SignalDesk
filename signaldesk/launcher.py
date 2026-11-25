"""Start and stop the desktop instance that owns the current data directory."""

import argparse
import errno
import json
import os
import re
import subprocess
import sys
import time
import webbrowser
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from typing import NamedTuple
from uuid import uuid4

from .security import data_directory

PORT_UNAVAILABLE = 98


class Instance(NamedTuple):
    generation: str
    port: int
    ready: bool

    def stop_request(self, directory: Path) -> Path:
        return directory / f"desktop-{self.generation}.stop"


def _try_lock(stream):
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return False
        raise
    return True


@contextmanager
def claim_instance(directory: Path, port: int):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "instance.lock").open("a+b", buffering=0) as stream:
        # A status reader briefly acquires an idle lock to check for a dead owner.
        if not _try_lock(stream):
            time.sleep(0.05)
            if not _try_lock(stream):
                yield None
                return
        # Byte zero is the original desktop lock. The rest is readable while locked.
        instance = Instance(uuid4().hex, port, False)
        stream.truncate(1)
        stream.seek(1)
        stream.write(f"{instance.generation} {port}".encode("ascii"))
        def mark_ready():
            stream.write(b" ready")

        try:
            yield instance, mark_ready
        finally:
            stream.truncate(1)
            instance.stop_request(directory).unlink(missing_ok=True)


def active_instance(directory: Path) -> Instance | None:
    try:
        stream = (directory / "instance.lock").open("r+b", buffering=0)
    except FileNotFoundError:
        return None
    with stream:
        if _try_lock(stream):
            return None
        stream.seek(1)
        match = re.fullmatch(rb"([a-f0-9]{32}) (\d{1,5})( ready)?", stream.read(64))
        if match is None:
            return Instance("", 0, False)  # Older desktop or a launch still publishing its identity.
        return Instance(match[1].decode("ascii"), int(match[2]), bool(match[3]))


def stop_desktop(directory: Path, timeout=60):
    instance = active_instance(directory)
    if instance is None:
        print("SignalDesk is already stopped.")
        return
    if not instance.generation:
        raise RuntimeError("Instance is starting or predates this script. Retry or exit it from its tray/console.")
    request = instance.stop_request(directory)
    request.touch()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = active_instance(directory)
        if current is None or (current.generation and current.generation != instance.generation):
            request.unlink(missing_ok=True)
            print("SignalDesk stopped.")
            return
        time.sleep(0.2)
    raise RuntimeError("Stop requested. SignalDesk has not finished shutting down.")


def start_desktop(directory: Path, port: int, background: bool, *, lan: bool = False):
    child = None
    if active_instance(directory) is None:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        print("Starting SignalDesk...", flush=True)
        arguments = [str(pythonw), "-m", "signaldesk.desktop", "--background", "--port", str(port)]
        if lan:
            arguments.append("--lan")
        child = subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    wait_for_desktop(directory, port, background, child)


def already_running(port: int) -> bool:
    connection = HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        payload = json.loads(response.read(1024))
        return response.status == 200 and isinstance(payload, dict) and payload.get("app") == "SignalDesk"
    except (OSError, HTTPException, ValueError):
        return False
    finally:
        connection.close()


def wait_for_desktop(directory: Path, port: int, background: bool, child=None, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        instance = active_instance(directory)
        if instance and instance.ready and not instance.stop_request(directory).exists():
            if not background:
                webbrowser.open(f"http://127.0.0.1:{instance.port}")
            return
        exit_code = child.poll() if child is not None else None
        if exit_code == PORT_UNAVAILABLE:
            raise RuntimeError(f"Cannot bind to 127.0.0.1:{port}. Check the port or use Start-SignalDesk.cmd --port PORT.")
        if exit_code not in (None, 0):
            raise RuntimeError(
                f"SignalDesk failed to start. Check port {port}, or run "
                fr".venv\Scripts\python.exe -m signaldesk.desktop --headless --port {port} for details."
            )
        if not instance and (child is None or exit_code is not None):
            raise RuntimeError("SignalDesk exited before it was ready. Run Start-SignalDesk.cmd again.")
        # An older running version only publishes the health endpoint.
        if instance and not instance.generation and already_running(port):
            if not background:
                webbrowser.open(f"http://127.0.0.1:{port}")
            return
        time.sleep(0.2)
    raise RuntimeError("SignalDesk has not reported ready yet. Run Start-SignalDesk.cmd again to check.")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)
    start = commands.add_parser("start")
    start.add_argument("--port", type=int, default=8765)
    start.add_argument("--background", action="store_true")
    start.add_argument("--lan", action="store_true")
    commands.add_parser("stop")
    args = parser.parse_args()
    try:
        if args.action == "stop":
            stop_desktop(data_directory())
        elif not 1 <= args.port <= 65535:
            parser.error("port must be between 1 and 65535")
        else:
            start_desktop(data_directory(), args.port, args.background, lan=args.lan)
    except (OSError, RuntimeError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
