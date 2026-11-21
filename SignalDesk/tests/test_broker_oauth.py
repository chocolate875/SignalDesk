import asyncio
import base64
import hashlib
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import longbridge.openapi as lp
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from signaldesk.app import create_app
from signaldesk.broker_oauth import CALLBACK, BrokerOAuth, InvalidGrant, OAuthError
from signaldesk.providers import LongPortFeed
from signaldesk.security import Vault

LEGACY = {"app_key": "old-key", "app_secret": "old-secret", "access_token": "old-token"}
ISSUED = {
    "access_token": "test-access",
    "refresh_token": "test-refresh",
    "token_type": "Bearer",
    "expires_in": 3600,
}


@pytest.fixture
def oauth(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALDESK_VAULT_KEY", Fernet.generate_key().decode())
    return BrokerOAuth(Vault(tmp_path))


async def test_authorization_callback_requires_browser_state_and_stores_only_after_success(
    oauth, monkeypatch
):
    post = AsyncMock(side_effect=[{"client_id": "test-client"}, ISSUED])
    monkeypatch.setattr(oauth, "_post", post)
    oauth.vault.save("longport", LEGACY)
    redirect = "http://localhost:9999" + CALLBACK
    url, browser = await oauth.start(redirect)
    query = parse_qs(urlsplit(url).query)
    assert query["scope"] == ["account.read watchlist"] and query["redirect_uri"] == [redirect]
    assert query["code_challenge_method"] == ["S256"]
    state = query["state"][0]
    assert await oauth.finish(state, "another-browser", "unused", False) == "invalid"
    assert await oauth.finish("bad-state", browser, "unused", False) == "invalid"
    assert oauth.vault.load("longport") == LEGACY
    assert await oauth.finish(state, browser, "one-use-code", False) == "success"
    grant = post.await_args.kwargs["data"]
    assert grant["client_id"] == "test-client" and grant["code"] == "one-use-code"
    assert grant["redirect_uri"] == redirect and grant["grant_type"] == "authorization_code"
    challenge = base64.urlsafe_b64encode(hashlib.sha256(grant["code_verifier"].encode()).digest())
    assert query["code_challenge"] == [challenge.decode().rstrip("=")]
    assert await oauth.finish(state, browser, "one-use-code", False) == "invalid"
    assert post.await_count == 2
    stored = await BrokerOAuth(oauth.vault).credentials()
    assert stored["refresh_token"] == "test-refresh" and "app_secret" not in stored
    assert b"test-refresh" not in (oauth.vault.directory / "longport.encrypted").read_bytes()
    assert oauth.status() == {"method": "oauth", "pending": False, "message": ""}


async def test_failed_expired_and_superseded_logins_keep_existing_account(oauth, monkeypatch):
    post = AsyncMock(side_effect=[{"client_id": "test-client"}, OAuthError("暂时无法兑换授权码")])
    monkeypatch.setattr(oauth, "_post", post)
    oauth.vault.save("longport", LEGACY)
    for outcome in ("replaced", "cancelled", "expired", "failed"):
        url, browser = await oauth.start("http://localhost:8765" + CALLBACK)
        state = parse_qs(urlsplit(url).query)["state"][0]
        if outcome == "replaced":
            await oauth.start("http://localhost:8765" + CALLBACK)
        elif outcome == "expired":
            oauth.pending.deadline = 0
        result = await oauth.finish(state, browser, "code", outcome == "cancelled")
        assert result == ("invalid" if outcome in {"replaced", "expired"} else outcome)
        assert oauth.vault.load("longport") == LEGACY
    assert post.await_count == 2


async def test_refresh_serializes_rotation_and_handles_revocation(oauth, monkeypatch):
    record = {
        "method": "oauth",
        "client_id": "client",
        "access_token": "old",
        "refresh_token": "original",
        "renew_at": 0,
    }
    oauth.vault.save("longport", record)
    renewed = {key: value for key, value in ISSUED.items() if key != "refresh_token"}
    post = AsyncMock(side_effect=[renewed, ISSUED, InvalidGrant("重新登录")])
    monkeypatch.setattr(oauth, "_post", post)
    first, second = await asyncio.gather(oauth.credentials(), oauth.credentials())
    assert first == second and first["refresh_token"] == "original" and post.await_count == 1
    oauth.vault.save("longport", {**second, "renew_at": 0})
    rotated = await oauth.credentials()
    assert rotated["refresh_token"] == ISSUED["refresh_token"]
    oauth.vault.save("longport", {**rotated, "renew_at": 0})
    with pytest.raises(InvalidGrant):
        await oauth.credentials()
    with pytest.raises(OAuthError):
        await oauth.credentials()
    assert post.await_count == 3 and oauth.vault.load("longport")["requires_login"]


def test_browser_api_guards_callback_and_keeps_tokens_out_of_responses(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALDESK_VAULT_KEY", Fernet.generate_key().decode())
    app = create_app(tmp_path, background=False)
    oauth = app.state.monitor.oauth
    monkeypatch.setattr(oauth, "_post", AsyncMock(side_effect=[{"client_id": "test-client"}, ISSUED]))
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.post("/api/broker/oauth/start").status_code == 401
        client.get("/api/bootstrap")
        assert (
            client.post("/api/broker/oauth/start", headers={"Origin": "https://else.invalid"}).status_code
            == 403
        )
        start = client.post("/api/broker/oauth/start")
        assert "HttpOnly" in start.headers["set-cookie"] and "SameSite=lax" in start.headers["set-cookie"]
        state = parse_qs(urlsplit(start.json()["url"]).query)["state"][0]
        result = client.get(
            CALLBACK,
            params={"state": state, "code": "test-code"},
            headers={"Sec-Fetch-Site": "cross-site"},
            follow_redirects=False,
        )
        assert result.status_code == 303 and result.headers["location"] == "/?broker-result=success"
        assert (
            result.headers["cache-control"] == "no-store"
            and result.headers["referrer-policy"] == "no-referrer"
        )
        settings = client.get("/api/settings")
        assert settings.json()["broker_auth"]["method"] == "oauth"
        assert settings.json()["settings"]["mode"] == "demo"
        assert not any(secret in settings.text for secret in ("test-code", "test-access", "test-refresh"))
        assert (
            client.post("/api/credentials", json={"service": "longport", "app_key": "partial"}).status_code
            == 400
        )
        assert oauth.vault.load("longport")["method"] == "oauth"
        assert client.post("/api/credentials", json={"service": "longport", **LEGACY}).is_success
        assert oauth.vault.load("longport") == LEGACY


async def test_installed_sdk_sends_vault_bearer_without_hmac(monkeypatch):
    headers = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            headers.update({k.lower(): v for k, v in self.headers.items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"code":0,"message":"ok","data":{}}')

        def log_message(self, *args):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            config = Mock()
            monkeypatch.setattr(lp, "Config", config)
            monkeypatch.setattr(lp, "QuoteContext", Mock())
            monkeypatch.setattr(lp, "TradeContext", Mock())
            LongPortFeed(
                {
                    "method": "oauth",
                    "platform": "longbridge",
                    "client_id": "test-client",
                    "access_token": "us_test-token",
                    "renew_at": 1234,
                },
                Mock(),
            )
            args, options = config.from_apikey.call_args
            assert options["http_url"] == "https://openapi.longbridge.com"
            client = lp.HttpClient.from_apikey(*args, http_url=f"http://127.0.0.1:{server.server_port}")
            await client.request_async("GET", "/wire-check")
        finally:
            server.shutdown()
            worker.join()
    assert headers["authorization"] == "Bearer us_test-token" and headers["x-api-key"] == "test-client"
    assert headers["x-dc-region"] == "us" and "x-api-signature" not in headers
