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


def test_default_daily_view_quote_and_codex_share_the_same_close(client):
    dashboard = client.get("/api/bootstrap").json()
    detail = client.get("/api/stock/NVDA.US").json()
    current, previous = detail["rows"][-1], detail["rows"][-2]
    stock = detail["stock"]
    assert len(detail["rows"]) > 750 and detail["timeframe"] == "day"
    assert stock["quote"]["last"] == stock["long_plan"]["close"] == current["close"]
    assert stock["quote"]["prev_close"] == previous["close"]
    assert stock["quote"]["timestamp"] == detail["summary"]["as_of"]
    preview = client.get("/api/analysis/preview/NVDA.US").json()
    assert preview["investment_horizon"] == "long"
    assert preview["technical"]["day:regular"]["as_of"] == detail["summary"]["as_of"]
    assert preview["research"]["curve"]["as_of"] == dashboard["curve"]["as_of"]
    assert all(event["sleeve"] == "long" for event in dashboard["events"])


def test_favorites_toggle_and_watchlist_sync_endpoints(client):
    dashboard = client.get("/api/bootstrap").json()
    assert len(dashboard["watchlist_groups"]) >= 1
    assert all("verdict" in stock and "action" in stock["verdict"] for stock in dashboard["stocks"])

    fav = client.put("/api/favorites/MSFT.US", json={"favorite": True})
    assert fav.status_code == 200 and fav.json() == {"symbol": "MSFT.US", "favorite": True}
    msft = next(s for s in client.get("/api/dashboard").json()["stocks"] if s["symbol"] == "MSFT.US")
    assert msft["favorite"] is True

    # Updating plan without specifying favorite preserves favorite=True.
    saved = client.put(
        "/api/allocations",
        json={
            "symbol": "MSFT.US",
            "name": "微软",
            "long_quantity": 12,
            "short_quantity": 0,
            "long_stop_price": 390,
            "long_target_price": 470,
        },
    )
    assert saved.status_code == 200 and saved.json()["favorite"] is True

    unfav = client.put("/api/favorites/MSFT.US", json={"favorite": False})
    assert unfav.status_code == 200 and unfav.json()["favorite"] is False

    sync_res = client.post("/api/watchlist/sync")
    assert sync_res.status_code == 200 and sync_res.json()["ok"] is True
    assert sync_res.json()["groups_count"] >= 1

    # Broker watchlist stock cannot be deleted locally, whereas manual local watch stock can.
    assert client.delete("/api/watchlist/META.US").status_code == 400
    assert (
        client.put(
            "/api/allocations",
            json={"symbol": "ORCL.US", "name": "甲骨文", "watch_only": True},
        ).status_code
        == 200
    )
    assert client.delete("/api/watchlist/ORCL.US").status_code == 200


def test_forecast_levels_rating_and_safe_snapshot_privacy(client):
    dashboard = client.get("/api/bootstrap").json()
    summary = dashboard["summary"]
    assert {"buy_rated", "hold_rated", "sell_rated"}.issubset(summary)
    assert (
        summary["buy_rated"] + summary["hold_rated"] + summary["sell_rated"]
        <= summary["count"]
    )

    for stock in dashboard["stocks"]:
        fc = stock["forecast"]
        lv = fc["levels"]
        rt = fc["rating"]
        assert lv["available"] is True and rt["available"] is True
        close = stock["long_plan"]["close"]
        assert (
            0
            < lv["stop_loss"]
            < lv["buy_low"]
            < lv["buy_high"]
            <= close
            < lv["sell_low"]
            < lv["sell_high"]
        )
        assert rt["code"] in {"strong_buy", "buy", "hold", "reduce", "sell"}
        wt = stock["wave_trend"]
        assert wt["available"] is True
        assert wt["trend"]["direction"] in {"uptrend", "downtrend", "sideways"}
        assert wt["trend"]["channel"]["available"] is True

    preview = client.get("/api/analysis/preview/NVDA.US").json()
    assert "forecast" in preview
    assert "wave_trend" in preview and preview["wave_trend"]["available"] is True
    assert preview["forecast"]["rating"]["code"] in {"strong_buy", "buy", "hold", "reduce", "sell"}
    assert "broker_quantity" not in str(preview)
    assert "cost_price" not in str(preview)
    assert "net_assets" not in str(preview)
