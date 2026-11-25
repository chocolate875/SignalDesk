import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from signaldesk.app import create_app


def test_lan_login_read_only_and_websocket(tmp_path, monkeypatch):
    from signaldesk import service

    async def no_start(self, background):
        pass

    monkeypatch.setattr(service.Monitor, "start", no_start)
    app = create_app(tmp_path, background=False, lan=True)
    host = "http://192.168.1.10:8765"
    stream = "ws://192.168.1.10:8765/api/stream"
    headers = {"Origin": host}
    remote = TestClient(app, base_url=host, client=("192.168.1.11", 54321))
    with TestClient(app) as local:
        assert remote.get("/api/bootstrap").status_code == 401
        assert remote.get("/api/settings").status_code == 403
        assert remote.get("/", headers={"Host": "untrusted.example"}).status_code == 403
        assert remote.get("/api/bootstrap", headers={"Host": "localhost"}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with remote.websocket_connect(stream, headers=headers):
                pass

        local_stock = local.get("/api/bootstrap").json()["stocks"][0]
        assert "broker_quantity" in local_stock
        code = local.get("/api/settings").json()["lan"]["code"]
        assert remote.post("/api/lan/login", json={"code": "wrong"}, headers=headers).status_code == 401
        assert remote.post("/api/lan/login", json={"code": code}, headers={"Origin": "http://other"}).status_code == 403
        assert remote.post("/api/lan/login", json={"code": code}, headers=headers).status_code == 200
        snapshot = remote.get("/api/bootstrap")
        assert snapshot.status_code == 200
        assert "ws://192.168.1.10:8765" in snapshot.headers["content-security-policy"]
        assert "broker_quantity" not in snapshot.json()["stocks"][0]
        stock = remote.get("/api/stock/NVDA.US").json()["stock"]
        assert "cost_price" not in stock and "verdict" not in stock
        assert remote.put("/api/favorites/NVDA.US", json={"favorite": True}, headers=headers).status_code == 403
        assert remote.get("/api/settings").status_code == 403
        with remote.websocket_connect(stream, headers=headers) as socket:
            assert "broker_quantity" not in socket.receive_json()["stocks"][0]

        public = TestClient(app, base_url=host, client=("203.0.113.16", 54321))
        assert public.get("/api/health", headers={"X-Forwarded-For": "192.168.1.11"}).status_code == 403


def test_loopback_default_rejects_lan_requests(tmp_path):
    app = create_app(tmp_path, background=False)
    try:
        client = TestClient(app, base_url="http://192.168.1.10:8765", client=("192.168.1.11", 54321))
        assert client.get("/api/health").status_code == 400
    finally:
        app.state.monitor.store.close()
