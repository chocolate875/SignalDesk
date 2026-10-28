from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

import httpx

from .models import NotificationEnvelope, QQSettings
from .security import Vault
from .storage import Store


@dataclass
class DeliveryResult:
    status: str
    detail: str
    retryable: bool = False
    retry_after: float = 0


class NotificationChannel(Protocol):
    async def send(self, envelope: NotificationEnvelope) -> DeliveryResult: ...
    async def health(self) -> dict: ...


def qq_text(event: NotificationEnvelope) -> str:
    # Allowlisted fields only. Never append a raw portfolio object or arbitrary analysis context.
    source = "【测试】" if event.source == "test" else "【演示】" if event.source == "demo" else ""
    score = f"\n技术结构评分 {event.score:.1f}/100" if event.score is not None else ""
    return (
        f"{source}SignalDesk · {event.title}\n{event.symbol} · {event.timeframe} · {event.session}"
        f"{score}\n{event.message[:350]}\n数据时间 {event.data_as_of}\n事件 {event.event_id[:8]}\n仅监控提醒，未执行交易"
    )[:1500]


class QQOfficial:
    API = "https://api.bot.qq.com"

    def __init__(self, vault: Vault, settings: QQSettings, client: httpx.AsyncClient | None = None):
        self.vault, self.settings = vault, settings
        self.client = client or httpx.AsyncClient(timeout=12, trust_env=False)
        self.access_token = ""
        self.expires_at = 0.0
        self._lock = asyncio.Lock()
        self.last_status = "disabled" if not settings.enabled else "unconfigured"
        self.last_detail = "QQ通道未启用" if not settings.enabled else "等待本机配置和平台授权"

    def configure(self, settings: QQSettings):
        if settings.app_id != self.settings.app_id:
            self.access_token, self.expires_at = "", 0
        self.settings = settings
        self.last_status = "ready" if self.ready() else "disabled" if not settings.enabled else "unconfigured"
        self.last_detail = (
            "已配置，等待平台投递验证"
            if self.ready()
            else "QQ通道未启用"
            if not settings.enabled
            else "等待本机配置与授权"
        )

    def ready(self):
        return bool(
            self.settings.enabled
            and self.settings.app_id
            and self.settings.target_openid
            and self.vault.configured("qq")
        )

    async def _token(self, force=False) -> str:
        async with self._lock:
            if not force and self.access_token and time.monotonic() < self.expires_at - 50:
                return self.access_token
            credentials = self.vault.load("qq")
            response = await self.client.post(
                f"{self.API}/app/getAppAccessToken",
                json={"appId": self.settings.app_id, "clientSecret": credentials.get("app_secret", "")},
            )
            payload = response.json()
            if (
                response.is_error
                or payload.get("code", 0) not in [0, None]
                or not payload.get("access_token")
            ):
                raise ValueError(f"QQ凭据验证失败，错误码 {payload.get('code', response.status_code)}")
            self.access_token = payload["access_token"]
            self.expires_at = time.monotonic() + max(0, float(payload.get("expires_in", 0)))
            return self.access_token

    async def send(self, envelope: NotificationEnvelope) -> DeliveryResult:
        if not self.ready():
            return DeliveryResult("blocked", "QQ未配置完整或未启用")
        # An OpenID belongs to this AppID; it must never be treated as a raw QQ numeric UIN.
        from urllib.parse import quote

        target = quote(self.settings.target_openid, safe="")
        kind = "users" if self.settings.target_kind == "user" else "groups"
        try:
            for attempt in range(2):
                token = await self._token(force=attempt == 1)
                response = await self.client.post(
                    f"{self.API}/v2/{kind}/{target}/messages",
                    headers={"Authorization": f"QQBot {token}", "X-Union-Appid": self.settings.app_id},
                    json={"content": qq_text(envelope), "msg_type": 0},
                )
                payload = response.json()
                code = int(payload.get("err_code", payload.get("code", 0)) or 0)
                if (response.status_code == 401 or code in {11241, 11243}) and attempt == 0:
                    continue
                if code in {11253, 304064, 40034105, 40034101, 40054003}:
                    result = DeliveryResult("blocked", f"QQ待授权/目标不可用，平台错误码 {code}")
                elif response.status_code == 429 or code in {40034100, 100001, 1100100}:
                    try:
                        retry_after = min(3600, max(5, float(response.headers.get("Retry-After", 30))))
                    except ValueError:
                        retry_after = 30
                    result = DeliveryResult("limited", f"QQ平台限流，错误码 {code or 429}", True, retry_after)
                elif response.is_success and code == 0 and payload.get("id"):
                    result = DeliveryResult("delivered", f"平台已接收，消息ID {str(payload['id'])[:48]}")
                elif response.status_code >= 500 or code in {50055001, 50055006}:
                    result = DeliveryResult(
                        "failed", f"QQ暂时不可用，错误码 {code or response.status_code}", True, 10
                    )
                else:
                    result = DeliveryResult(
                        "blocked", f"QQ发送未成功，平台错误码 {code or response.status_code}"
                    )
                self.last_status, self.last_detail = result.status, result.detail
                return result
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return DeliveryResult("failed", "QQ连接失败", True, 10)
        except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.RemoteProtocolError):
            return DeliveryResult("unknown", "QQ请求结果未知，请核对接收端后重试")
        except (ValueError, KeyError):
            return DeliveryResult("blocked", "QQ认证或响应格式异常，请检查本机凭据与平台权限")
        return DeliveryResult("blocked", "QQ认证失败")

    async def health(self) -> dict:
        return {
            "configured": self.ready(),
            "status": self.last_status,
            "detail": self.last_detail,
            "target_kind": self.settings.target_kind,
        }


class DesktopChannel:
    def __init__(self):
        self.sender = None

    async def send(self, envelope: NotificationEnvelope) -> DeliveryResult:
        if self.sender is None:
            return DeliveryResult("unavailable", "托盘未运行，提醒已保留在本机看板")
        try:
            await asyncio.to_thread(
                self.sender, f"{envelope.symbol} · {envelope.message[:180]}", envelope.title
            )
            return DeliveryResult("submitted", "已提交Windows本地通知；是否显示由系统通知设置决定")
        except Exception:
            return DeliveryResult("failed", "系统通知不可用，提醒已保留在看板")

    async def health(self):
        return {"status": "ready" if self.sender else "unavailable", "configured": self.sender is not None}


class NotificationDispatcher:
    def __init__(self, store: Store, vault: Vault, settings: QQSettings):
        self.store = store
        self.qq = QQOfficial(vault, settings)
        self.desktop = DesktopChannel()
        self.delivery_enabled = True
        self.pause_ordinary = False

    def enqueue(self, event: dict, desktop: bool, qq: bool):
        envelope = NotificationEnvelope(**{k: event[k] for k in NotificationEnvelope.model_fields})
        if desktop:
            self.store.enqueue(event["id"], "desktop", "local", envelope.model_dump())
        if qq and self.qq.ready():
            target = (
                f"{self.qq.settings.app_id}:{self.qq.settings.target_kind}:{self.qq.settings.target_openid}"
            )
            self.store.enqueue(
                event["id"],
                "qq",
                target,
                envelope.model_dump(),
                time.time() + 30 if envelope.severity == "info" else 0,
            )

    async def tick(self):
        if not self.delivery_enabled:
            return
        items = self.store.due(time.time(), self.pause_ordinary)
        grouped = {}
        for item in items:
            envelope = NotificationEnvelope.model_validate(json.loads(item["payload"]))
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(envelope.data_as_of)).total_seconds()
            if age > (86400 if envelope.severity == "critical" else 3600):
                self.store.delivery(item["id"], "expired", "历史提醒已过期，保留在本机记录", item["attempts"])
                continue
            key = (item["channel"], item["target"], "ordinary" if envelope.severity == "info" else item["id"])
            grouped.setdefault(key, []).append((item, envelope))
        for group in grouped.values():
            item, envelope = group[0]
            if len(group) > 1:
                content = "；".join(
                    f"{e.symbol} {e.title} {e.score:.1f}分"
                    if e.score is not None
                    else f"{e.symbol} {e.title}"
                    for _, e in group
                )
                envelope = envelope.model_copy(
                    update={
                        "event_id": str(uuid5(NAMESPACE_URL, ":".join(e.event_id for _, e in group))),
                        "symbol": "MULTI",
                        "title": f"{len(group)}项普通技术信号汇总",
                        "message": content[:350],
                    }
                )
            for entry, _ in group:
                self.store.delivery(entry["id"], "sending", "发送中", entry["attempts"] + 1)
            channel = self.qq if item["channel"] == "qq" else self.desktop
            if item["channel"] == "qq":
                current_target = f"{self.qq.settings.app_id}:{self.qq.settings.target_kind}:{self.qq.settings.target_openid}"
                if current_target != item["target"]:
                    for entry, _ in group:
                        self.store.delivery(
                            entry["id"],
                            "cancelled",
                            "目标已修改，旧提醒未转发到新目标",
                            entry["attempts"] + 1,
                        )
                    continue
            try:
                result = await channel.send(envelope)
            except Exception:
                result = DeliveryResult("failed", "通知通道异常，事件已保留在本机")
            for entry, _ in group:
                attempts = entry["attempts"] + 1
                retry = result.retryable and attempts < 3
                self.store.delivery(
                    entry["id"],
                    "pending" if retry else result.status,
                    result.detail,
                    attempts,
                    time.time() + max(result.retry_after, 2**attempts),
                )

    async def run(self):
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # Next iteration leaves the monitor alive; sending rows remain visible.
            await asyncio.sleep(1)

    async def close(self):
        await self.qq.client.aclose()
