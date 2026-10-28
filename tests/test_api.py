import pytest
from fastapi.testclient import TestClient

from signaldesk.app import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    app = create_app(tmp_path_factory.mktemp("api"), background=False)
    with TestClient(app) as value:
        yield value


def test_api_local_session_and_cross_origin_boundary(client):
    assert client.get("/api/health").json()["app"] == "SignalDesk"
    assert client.get("/api/settings").status_code == 401
    response = client.get("/api/bootstrap")
    assert response.status_code == 200 and response.json()["mode"] == "demo"
    assert len(response.json()["stocks"]) == 8
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/dashboard", headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert client.get("/api/bootstrap", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_detail_and_send_preview_do_not_expose_account_fields(client):
    client.get("/api/bootstrap")
    detail = client.get("/api/stock/NVDA.US?timeframe=15m&session=regular").json()
    assert detail["rows"] and detail["summary"]["score"] is not None
    preview = client.get("/api/analysis/preview/NVDA.US").json()
    assert preview["source"] == "demo"
    assert "broker_quantity" not in str(preview) and "cost_price" not in str(preview)
    assert client.get("/api/stock/NVDA.US?timeframe=1s").status_code == 400
    assert client.post("/api/orders", json={}).status_code in [404, 405]


def test_weights_invalid_and_oversubscribed_allocation_rejected(client):
    client.get("/api/bootstrap")
    settings = client.get("/api/settings").json()["settings"]
    settings["rules"]["trend_weight"] = 0.9
    assert client.put("/api/settings", json=settings).status_code == 422
    result = client.put(
        "/api/allocations", json={"symbol": "NVDA.US", "long_quantity": 999999, "short_quantity": 0}
    )
    assert result.status_code == 400
    assert client.get("/api/settings").json()["credentials"] == {"longport": False, "qq": False}
