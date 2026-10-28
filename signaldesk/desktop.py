from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from .app import create_app
from .security import data_directory


def server_config(app, port: int):
    options = {}
    if sys.stdout is None or sys.stderr is None:
        # pythonw has no console streams. Uvicorn's default formatter calls stdout.isatty().
        # Operational failures are exposed through local status; never dump requests/account data.
        options["log_config"] = {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {"silent": {"class": "logging.NullHandler"}},
            "loggers": {
                name: {"handlers": ["silent"], "level": "WARNING", "propagate": False}
                for name in ["uvicorn", "uvicorn.error", "uvicorn.access"]
            },
        }
    return uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False, **options)


def already_running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            return json.load(response).get("app") == "SignalDesk"
    except Exception:
        return False


def icon_image(color="#6de0bc"):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (15, 20, 29, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=16, fill="#172330")
    draw.line([(13, 40), (23, 31), (31, 37), (43, 19), (52, 24)], fill=color, width=5)
    return image


def main():
    parser = argparse.ArgumentParser(description="SignalDesk本机技术信号看板")
    parser.add_argument("--headless", action="store_true", help="无托盘模式，适用于Linux/本地服务")
    parser.add_argument("--background", action="store_true", help="后台启动，只显示托盘")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"
    if already_running(args.port):
        if not args.background:
            webbrowser.open(url)
        return
    directory = data_directory()
    directory.mkdir(parents=True, exist_ok=True)
    # A second launch must not initialise the same SQLite queue before the first owns the service.
    lock_file = (directory / "instance.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        if not args.background:
            webbrowser.open(url)
        return
    app = create_app(directory)
    config = server_config(app, args.port)
    server = uvicorn.Server(config)
    if args.headless or os.name != "nt":
        try:
            server.run()
        finally:
            lock_file.close()
        return
    import pystray

    def open_panel(icon=None, item=None):
        webbrowser.open(url)

    def pause(icon, item):
        monitor = app.state.monitor
        value = monitor.settings.model_copy(deep=True)
        value.pause_ordinary = not value.pause_ordinary
        monitor.update_settings(value)
        icon.update_menu()

    def quit_app(icon, item):
        server.should_exit = True
        icon.stop()

    icon = pystray.Icon(
        "SignalDesk",
        icon_image(),
        "SignalDesk · 正在启动",
        menu=pystray.Menu(
            pystray.MenuItem("打开看板", open_panel, default=True),
            pystray.MenuItem(
                "暂停普通提醒（重要风险继续）",
                pause,
                checked=lambda item: app.state.monitor.settings.pause_ordinary,
            ),
            pystray.MenuItem("设置与开机自启", open_panel),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出并停止监控", quit_app),
        ),
    )
    worker = threading.Thread(target=server.run, daemon=True, name="signaldesk-service")
    worker.start()

    def setup(tray):
        tray.visible = True
        app.state.monitor.notifications.desktop.sender = lambda message, title: tray.notify(message, title)
        if not args.background:
            for _ in range(90):
                if server.started:
                    webbrowser.open(url)
                    break
                time.sleep(0.2)
        previous = None
        while not server.should_exit:
            status = app.state.monitor.status
            tray.title = f"SignalDesk · {status} · 后台监控"
            if status != previous:
                tray.icon = icon_image("#6de0bc" if status in {"live", "demo"} else "#efb86b")
                previous = status
            time.sleep(2)

    try:
        icon.run(setup)
    finally:
        server.should_exit = True
        worker.join(timeout=8)
        lock_file.close()


if __name__ == "__main__":
    main()
