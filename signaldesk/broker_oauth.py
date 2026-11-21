"""Longbridge public-client OAuth with SignalDesk's encrypted token storage."""

import asyncio
import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .security import Vault

OAUTH_BASE = "https://openapi.longbridge.com/oauth2"
CALLBACK = "/broker/oauth/callback"
FLOW_SECONDS = 600
REAUTHORIZE = "长桥授权已失效，请在设置中重新登录长桥。"


class OAuthError(ValueError):
    """Only user-facing messages, never provider response bodies."""


@dataclass
class PendingLogin:
    state: str
    browser: str
    verifier: str
    client_id: str
    redirect_uri: str
    deadline: float


class BrokerOAuth:
    def __init__(self, vault: Vault):
        self.vault = vault
        self.lock = asyncio.Lock()
        self.pending: PendingLogin | None = None
        self.message = ""

    def status(self):
        if self.pending and not self.lock.locked() and time.monotonic() >= self.pending.deadline:
            self.pending = None
            self.message = "本次授权已超时，请重试。"
        saved = self.vault.load("longport")
        return {
            "method": saved.get("method", "apikey") if saved else None,
            "pending": self.pending is not None,
            "message": self.message or (REAUTHORIZE if saved.get("requires_login") else ""),
        }

    async def _post(self, endpoint: str, **kwargs) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(f"{OAUTH_BASE}/{endpoint}", **kwargs)
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise OAuthError("暂时无法连接长桥授权服务，请稍后重试。") from None
        if not isinstance(payload, dict):
            raise OAuthError("长桥授权服务返回了无效响应，请重试。")
        if response.is_error or payload.get("error"):
            if payload.get("error") == "invalid_grant":
                raise InvalidGrant(REAUTHORIZE)
            raise OAuthError(f"长桥未接受授权请求（HTTP {response.status_code}），请重试。")
        return payload

    async def start(self, redirect_uri: str) -> tuple[str, str]:
        async with self.lock:
            registration = self.vault.load("longbridge_client")
            if registration.get("redirect_uri") != redirect_uri:
                result = await self._post(
                    "register",
                    json={
                        "client_name": "SignalDesk",
                        "redirect_uris": [redirect_uri],
                        "token_endpoint_auth_method": "none",
                        "grant_types": ["authorization_code", "refresh_token"],
                        "response_types": ["code"],
                    },
                )
                client_id = result.get("client_id")
                if not isinstance(client_id, str) or not client_id.strip():
                    raise OAuthError("长桥未返回客户端 ID，请重新尝试注册。")
                registration = {"client_id": client_id, "redirect_uri": redirect_uri}
                self.vault.save("longbridge_client", registration)
            flow = PendingLogin(
                state=secrets.token_urlsafe(32),
                browser=secrets.token_urlsafe(32),
                verifier=secrets.token_urlsafe(64),
                client_id=registration["client_id"],
                redirect_uri=redirect_uri,
                deadline=time.monotonic() + FLOW_SECONDS,
            )
            challenge = base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest())
            query = urlencode(
                {
                    "response_type": "code",
                    "client_id": flow.client_id,
                    "redirect_uri": redirect_uri,
                    "scope": "account.read watchlist",
                    "state": flow.state,
                    "code_challenge": challenge.decode().rstrip("="),
                    "code_challenge_method": "S256",
                }
            )
            self.pending, self.message = flow, ""
            return f"{OAUTH_BASE}/authorize?{query}", flow.browser

    async def finish(self, state: str, browser: str, code: str, denied: bool) -> str:
        async with self.lock:
            flow = self.pending
            if (
                not flow
                or time.monotonic() >= flow.deadline
                or not secrets.compare_digest(flow.state.encode(), state.encode())
                or not secrets.compare_digest(flow.browser.encode(), browser.encode())
            ):
                return "invalid"
            if denied or not code:
                self.pending = None
                self.message = "未完成长桥授权，可重新登录。"
                return "cancelled"
            try:
                await self._token(
                    flow.client_id,
                    {
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": flow.redirect_uri,
                        "code_verifier": flow.verifier,
                    },
                )
            except OAuthError as error:
                self.message = str(error)
                return "failed"
            except (ValueError, OSError):
                self.message = "授权未保存，请检查本机凭据库和网络后重试。"
                return "failed"
            finally:
                self.pending = None
            self.message = ""
            return "success"

    async def _token(self, client_id: str, grant: dict) -> dict:
        result = await self._post("token", data={"client_id": client_id, **grant})
        access = result.get("access_token")
        refresh = result.get("refresh_token") or grant.get("refresh_token")
        try:
            lifetime = int(result.get("expires_in", 3600))
        except (TypeError, ValueError, OverflowError):
            lifetime = 0
        if (
            not isinstance(access, str)
            or not access.strip()
            or lifetime <= 0
            or str(result.get("token_type", "")).lower() != "bearer"
            or (refresh is not None and not isinstance(refresh, str))
        ):
            raise OAuthError("长桥返回的令牌无效，请重新授权。")
        record = {
            "method": "oauth",
            "platform": "longbridge",
            "client_id": client_id,
            "access_token": access,
            "refresh_token": refresh,
            "renew_at": time.time() + lifetime - min(120, lifetime / 4),
        }
        self.vault.save("longport", record)
        return record

    async def credentials(self) -> dict:
        async with self.lock:
            saved = self.vault.load("longport")
            if saved.get("method") != "oauth":
                return saved
            if saved.get("requires_login"):
                raise OAuthError(REAUTHORIZE)
            if time.time() < saved["renew_at"]:
                return saved
            try:
                if not saved.get("refresh_token"):
                    raise InvalidGrant(REAUTHORIZE)
                return await self._token(
                    saved["client_id"],
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": saved["refresh_token"],
                    },
                )
            except InvalidGrant:
                self.vault.save("longport", {**saved, "requires_login": True})
                raise


class InvalidGrant(OAuthError):
    pass
