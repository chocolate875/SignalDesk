from __future__ import annotations

import argparse
import os
import socket
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor

import uvicorn

from .launcher import PORT_UNAVAILABLE, claim_instance, wait_for_desktop
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


def icon_image(color="#6de0bc"):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (15, 20, 29, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=16, fill="#172330")
    draw.line([(13, 40), (23, 31), (31, 37), (43, 19), (52, 24)], fill=color, width=5)
    return image


class DesktopServer(uvicorn.Server):
    def __init__(self, config, mark_ready, stop_request):
        super().__init__(config)
        self.mark_ready = mark_ready
        self.stop_request = stop_request

    async def main_loop(self):
        self.mark_ready()
        await super().main_loop()

    async def on_tick(self, counter):
        if counter % 5 == 0 and self.stop_request.exists():
            self.should_exit = True
        return await super().on_tick(counter)


def main():
    parser = argparse.ArgumentParser(description="SignalDesk本机技术信号看板")
    parser.add_argument("--headless", action="store_true", help="无托盘模式，适用于Linux/本地服务")
    parser.add_argument("--background", action="store_true", help="后台启动，只显示托盘")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    directory = data_directory()
    with claim_instance(directory, args.port) as owner:
        if owner is None:
            if not args.background and not args.headless:
                wait_for_desktop(directory, args.port, False)
            return
        instance, mark_ready = owner
        # Reserve the port before initialising the monitor or displaying a tray icon.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            option = socket.SO_EXCLUSIVEADDRUSE if os.name == "nt" else socket.SO_REUSEADDR
            listener.setsockopt(socket.SOL_SOCKET, option, 1)
            try:
                listener.bind(("127.0.0.1", args.port))
                listener.listen()
            except OSError as exc:
                if sys.stderr is not None:
                    print(f"Cannot bind to 127.0.0.1:{args.port}: {exc}", file=sys.stderr)
                raise SystemExit(PORT_UNAVAILABLE) from exc
            from .app import create_app

            app = create_app(directory)
            server = DesktopServer(server_config(app, args.port), mark_ready, instance.stop_request(directory))
            if args.headless or os.name != "nt":
                server.run(sockets=[listener])
            else:
                run_tray(app, server, listener, args.background)


def run_tray(app, server, listener, background):
    import pystray

    def open_panel(icon=None, item=None):
        webbrowser.open(f"http://127.0.0.1:{server.config.port}")

    def pause(icon, item):
        monitor = app.state.monitor
        value = monitor.settings.model_copy(deep=True)
        value.pause_ordinary = not value.pause_ordinary
        monitor.update_settings(value)
        icon.update_menu()

    def quit_app(icon, item):
        server.should_exit = True

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

    def setup(tray):
        tray.visible = True
        app.state.monitor.notifications.desktop.sender = lambda message, title: tray.notify(message, title)
        open_when_ready = not background
        previous = None
        while not worker.done() and not server.should_exit:
            if server.started and open_when_ready:
                open_panel()
                open_when_ready = False
            status = app.state.monitor.status
            if server.started and status != previous:
                tray.title = f"SignalDesk · {status} · 后台监控"
                tray.icon = icon_image("#6de0bc" if status in {"live", "demo"} else "#efb86b")
                previous = status
            time.sleep(0.2)
        tray.stop()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="signaldesk-service") as executor:
        worker = executor.submit(server.run, sockets=[listener])
        try:
            icon.run(setup)
        finally:
            server.should_exit = True
        worker.result()


if __name__ == "__main__":
    main()
