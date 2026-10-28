from __future__ import annotations

import ctypes
import json
import os
import secrets
from pathlib import Path


def data_directory() -> Path:
    override = os.environ.get("SIGNALDESK_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "SignalDesk"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "signaldesk"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    buffer = ctypes.create_string_buffer(data)
    incoming = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = _Blob()
    crypt32 = ctypes.windll.crypt32
    if decrypt:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)
        )
    else:
        ok = crypt32.CryptProtectData(
            ctypes.byref(incoming), "SignalDesk credentials", None, None, None, 1, ctypes.byref(outgoing)
        )
    if not ok:
        raise OSError("Windows凭据加解密失败")
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.pbData)


class Vault:
    """Secrets never enter public settings, API responses, subprocess environments or Git."""

    def __init__(self, directory: Path):
        self.directory = directory / "credentials"
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, service: str) -> Path:
        if service not in {"qq", "longport"}:
            raise ValueError("未知凭据服务")
        return self.directory / f"{service}.encrypted"

    def save(self, service: str, value: dict):
        raw = json.dumps(value).encode()
        if os.name == "nt":
            encrypted = b"DPAPI1:" + _dpapi(raw)
        else:
            from cryptography.fernet import Fernet

            key = os.environ.get("SIGNALDESK_VAULT_KEY")
            if not key:
                raise ValueError("Linux实盘需先设置SIGNALDESK_VAULT_KEY；不会回退为明文保存")
            encrypted = b"FERNET1:" + Fernet(key.encode()).encrypt(raw)
        path = self._path(service)
        temp = path.with_suffix(".tmp")
        temp.write_bytes(encrypted)
        if os.name != "nt":
            temp.chmod(0o600)
        temp.replace(path)

    def load(self, service: str) -> dict:
        path = self._path(service)
        if not path.exists():
            return {}
        data = path.read_bytes()
        if data.startswith(b"DPAPI1:") and os.name == "nt":
            raw = _dpapi(data[7:], decrypt=True)
        elif data.startswith(b"FERNET1:"):
            from cryptography.fernet import Fernet

            raw = Fernet(os.environ["SIGNALDESK_VAULT_KEY"].encode()).decrypt(data[8:])
        else:
            raise ValueError("凭据不属于此系统或格式不受支持")
        return json.loads(raw)

    def configured(self, service: str) -> bool:
        return self._path(service).exists()


def session_token() -> str:
    return secrets.token_urlsafe(32)


def safe_child_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "APPDATA",
        "LOCALAPPDATA",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    # No LONGPORT_*, QQ_*, SIGNALDESK_VAULT_KEY or arbitrary inherited app credentials.
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def safe_snapshot(stock: dict, mode: str) -> dict:
    """Explicit allowlist instead of trying to redact an unbounded account object."""
    summaries = stock.get("summaries", {})
    return {
        "source": mode,
        "symbol": stock["symbol"],
        "name": stock.get("name", ""),
        "investment_horizon": stock.get("sleeves", ["unassigned"]),
        "position_weight_percent": stock.get("weight_percent"),
        "unrealized_return_percent": stock.get("pnl_percent"),
        "distance_to_stop_percent": stock.get("distance_to_stop_percent"),
        "market": {
            key: stock.get("quote", {}).get(key)
            for key in ["last", "timestamp", "trade_status", "spread_ratio"]
        },
        "technical": summaries,
    }
