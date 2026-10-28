import json
from pathlib import Path

import httpx
import pytest

from signaldesk.codex_bridge import command
from signaldesk.models import Allocation, NotificationEnvelope, QQSettings
from signaldesk.notifications import QQOfficial, qq_text
from signaldesk.security import Vault, safe_child_environment, safe_snapshot
from signaldesk.storage import Store


class FakeVault:
    def configured(self, service):
        return True

    def load(self, service):
        return {"app_secret": "SYNTHETIC_SECRET_DO_NOT_TRANSMIT"}


def envelope():
    return NotificationEnvelope(
        event_id="synthetic-event",
        symbol="TEST.US",
        timeframe="15m",
        session="regular",
        severity="warning",
        title="技术结构测试",
        message="合成测试",
        evidence=["趋势20分；动量25分"],
        rule_version="fusion-test",
        score=30,
        data_as_of="2026-10-28T01:00:00Z",
        source="test",
    )


@pytest.mark.asyncio
async def test_qq_official_token_reuse_and_business_response():
    calls = []

    def transport(request):
        calls.append(request)
        if request.url.path.endswith("getAppAccessToken"):
            return httpx.Response(200, json={"access_token": "synthetic-access", "expires_in": "7200"})
        assert request.headers["Authorization"] == "QQBot synthetic-access"
        assert request.url.path == "/v2/users/test-openid/messages"
        assert "msg_id" not in json.loads(request.content)
        assert "SYNTHETIC_SECRET" not in request.content.decode()
        assert "趋势20分" in json.loads(request.content)["content"]
        return httpx.Response(200, json={"id": "official-receipt"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        qq = QQOfficial(
            FakeVault(), QQSettings(enabled=True, app_id="test-app", target_openid="test-openid"), client
        )
        assert (await qq.send(envelope())).status == "delivered"
        assert (await qq.send(envelope())).status == "delivered"
        assert len([r for r in calls if r.url.path.endswith("getAppAccessToken")]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("code,expected", [(100001, "limited"), (100016, "blocked")])
async def test_qq_token_http_200_business_failure(code, expected):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": code}))
    ) as client:
        qq = QQOfficial(FakeVault(), QQSettings(enabled=True, app_id="test", target_openid="test"), client)
        assert (await qq.send(envelope())).status == expected
        assert (await qq.health())["status"] == expected


@pytest.mark.asyncio
async def test_qq_expired_token_refresh_and_failed_health():
    count = {"token": 0, "message": 0}

    def transport(request):
        if request.url.path.endswith("getAppAccessToken"):
            count["token"] += 1
            return httpx.Response(200, json={"access_token": f"token-{count['token']}", "expires_in": 7200})
        count["message"] += 1
        if count["message"] == 1:
            return httpx.Response(401, json={"code": 11243})
        if count["message"] == 2:
            return httpx.Response(200, json={"id": "refreshed-receipt"})
        raise httpx.ConnectError("synthetic disconnect", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        qq = QQOfficial(FakeVault(), QQSettings(enabled=True, app_id="test", target_openid="test"), client)
        assert (await qq.send(envelope())).status == "delivered"
        assert count == {"token": 2, "message": 2}
        assert (await qq.send(envelope())).status == "failed"
        assert (await qq.health())["status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,expected",
    [(40034105, "blocked"), (304064, "blocked"), (40034100, "limited"), (40054010, "blocked")],
)
async def test_qq_does_not_treat_http_200_error_as_sent(code, expected):
    def transport(request):
        if request.url.path.endswith("getAppAccessToken"):
            return httpx.Response(200, json={"access_token": "synthetic-access", "expires_in": 7200})
        return httpx.Response(200, json={"err_code": code, "message": "untrusted error text"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        qq = QQOfficial(
            FakeVault(),
            QQSettings(enabled=True, app_id="test-app", target_kind="group", target_openid="group-openid"),
            client,
        )
        result = await qq.send(envelope())
        assert result.status == expected
        assert str(code) in result.detail


def test_vault_encrypted_and_private_snapshot(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("SIGNALDESK_VAULT_KEY", Fernet.generate_key().decode())
    vault = Vault(tmp_path)
    vault.save("qq", {"app_secret": "TEST_ONLY_TOP_SECRET"})
    assert vault.load("qq")["app_secret"] == "TEST_ONLY_TOP_SECRET"
    assert b"TEST_ONLY_TOP_SECRET" not in (tmp_path / "credentials/qq.encrypted").read_bytes()
    stock = {
        "symbol": "TEST.US",
        "name": "demo",
        "broker_quantity": 1234,
        "cost_price": 88,
        "account_id": "TEST_ACCOUNT_ID",
        "net_assets": 999999,
        "weight_percent": 4.2,
        "pnl_percent": 1.2,
        "sleeves": ["long", "short"],
        "summaries": {},
        "quote": {"last": 100, "timestamp": "now"},
    }
    snapshot = safe_snapshot(stock, "demo")
    assert snapshot["position_weight_percent"] == 4.2
    encoded = json.dumps(snapshot)
    for field in ["broker_quantity", "cost_price", "account_id", "net_assets", "TEST_ACCOUNT_ID"]:
        assert field not in encoded
    monkeypatch.setenv("LONGPORT_ACCESS_TOKEN", "BROKER_CANARY")
    monkeypatch.setenv("QQ_APP_SECRET", "QQ_CANARY")
    child = safe_child_environment()
    assert "LONGPORT_ACCESS_TOKEN" not in child and "QQ_APP_SECRET" not in child
    assert "SIGNALDESK_VAULT_KEY" not in child
    assert "position_weight" not in qq_text(envelope())


def test_exact_codex_permissions_not_legacy_full_read(tmp_path):
    args = command("codex", tmp_path, {"model": "test-model"})
    assert "--ignore-user-config" in args and "--ephemeral" in args
    assert "--sandbox" not in args
    joined = " ".join(args)
    assert 'default_permissions="signaldesk-analysis"' in joined
    assert str(tmp_path).replace("\\", "\\\\") in joined
    assert "shell_tool" in args and "plugins" in args and "multi_agent" in args
    assert ":root" not in joined
    assert "--output-schema" in args
    import tomllib

    permissions_arg = next(value for value in args if value.startswith("permissions="))
    parsed = tomllib.loads(permissions_arg)["permissions"]["signaldesk-analysis"]
    assert set(parsed["filesystem"]) == {":minimal", str(tmp_path)}
    assert not parsed["network"]["enabled"]


def test_interrupted_delivery_and_dual_sleeve_reconciliation(tmp_path):
    store = Store(tmp_path)
    store.enqueue("one", "qq", "target", envelope().model_dump())
    item = store.due(1)[0]
    store.delivery(item["id"], "sending", "in flight", 1)
    store.close()
    store = Store(tmp_path)
    assert store.deliveries()[0]["status"] == "unknown"
    assert store.due(1) == []
    store.close()
    allocation = Allocation(symbol="NVDA", long_quantity=6, short_quantity=4, broker_quantity=10)
    assert allocation.reconciled and allocation.sleeves() == ["long", "short"]
    allocation.broker_quantity = 8
    assert not allocation.reconciled


def test_no_private_runtime_files_tracked():
    import subprocess

    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
    tracked = result.stdout.splitlines()
    assert not any(p.startswith((".runtime/", "data/", "logs/", ".private/")) for p in tracked)
    paths = b".runtime/codex-exports/snapshot.json\0data/account.sqlite3\0.env\0logs/private.log\0"
    ignored = subprocess.run(
        ["git", "check-ignore", "-z", "--stdin"], input=paths, cwd=root, capture_output=True
    )
    assert ignored.returncode == 0 and len(ignored.stdout.rstrip(b"\0").split(b"\0")) == 4
