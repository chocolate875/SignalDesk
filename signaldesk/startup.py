from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

NAME = "SignalDesk"
KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_command() -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return subprocess.list2cmdline([str(pythonw), "-m", "signaldesk.desktop", "--background"])


def state() -> dict:
    if os.name != "nt":
        return {
            "supported": False,
            "enabled": False,
            "detail": "Linux请使用用户级systemd服务；首版不修改系统服务",
        }
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            value, _ = winreg.QueryValueEx(key, NAME)
        return {
            "supported": True,
            "enabled": value == startup_command(),
            "detail": "登录后后台启动，托盘可见"
            if value == startup_command()
            else "启动项指向其他安装，请重新设置",
        }
    except FileNotFoundError:
        return {"supported": True, "enabled": False, "detail": "尚未启用，可随时手动打开"}
    except OSError:
        return {"supported": True, "enabled": False, "detail": "当前进程无权读取启动项"}


def set_enabled(enabled: bool) -> dict:
    if os.name != "nt":
        raise ValueError("当前系统不支持Windows启动项")
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as key:
        if enabled:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass
    return state()
