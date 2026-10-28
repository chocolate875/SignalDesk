from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import startup
from .models import Allocation, Credentials, NotificationEnvelope, Settings, utcnow
from .operators import REGISTRY
from .security import data_directory, safe_snapshot, session_token
from .service import Monitor
from .storage import Store


def local_origin(origin: str | None, host: str | None) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc == host


def create_app(directory: Path | None = None, background: bool = True) -> FastAPI:
    monitor = Monitor(Store(directory or data_directory()))
    token = session_token()

    @asynccontextmanager
    async def lifespan(application):
        await monitor.start(background)
        yield
        await monitor.stop()

    app = FastAPI(title="SignalDesk", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.monitor = monitor
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_session(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if (
                not local_origin(request.headers.get("origin"), request.headers.get("host"))
                or request.headers.get("sec-fetch-site") == "cross-site"
            ):
                return JSONResponse({"detail": "只接受本机同源请求"}, status_code=403)
            if request.url.path not in {"/api/bootstrap", "/api/health"}:
                if not secrets.compare_digest(request.cookies.get("signaldesk_session", ""), token):
                    return JSONResponse({"detail": "请从本机看板建立会话"}, status_code=401)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": str(exc)[:300]}, status_code=400)

    @app.get("/api/health")
    async def health():
        return {"app": "SignalDesk", "version": "0.1.0", "status": monitor.status}

    @app.get("/api/bootstrap")
    async def bootstrap():
        response = JSONResponse(await monitor.snapshot())
        response.set_cookie("signaldesk_session", token, httponly=True, samesite="strict")
        return response

    @app.get("/api/dashboard")
    async def dashboard():
        return await monitor.snapshot()

    @app.get("/api/stock/{symbol}")
    async def stock(symbol: str, timeframe: str = "15m", session: str = "regular"):
        if timeframe not in {"15m", "day"} or session not in {"regular", "pre", "post", "overnight"}:
            raise HTTPException(400, "不支持的周期或时段")
        normalized = Allocation(symbol=symbol).symbol
        return monitor.detail_for(normalized, timeframe, "regular" if timeframe == "day" else session)

    @app.put("/api/allocations")
    async def allocation(value: Allocation):
        saved = monitor.save_allocation(value)
        if monitor.settings.mode == "demo" and saved.symbol in {
            d[0] for d in __import__("signaldesk.demo", fromlist=["DEMO_NAMES"]).DEMO_NAMES
        }:
            await asyncio.to_thread(monitor.rebuild, saved.symbol, True)
        monitor.last_probe = 0
        return saved.model_dump()

    @app.delete("/api/watchlist/{symbol}")
    async def remove_watch(symbol: str):
        normalized = Allocation(symbol=symbol).symbol
        stocks = monitor.portfolio()
        item = next((a for a in stocks if a.symbol == normalized), None)
        if item and item.broker_quantity > 0:
            raise ValueError("券商持仓不能从监控列表删除，可调整分类和提醒规则")
        monitor.store.set(
            f"portfolio:{monitor.settings.mode}", [a.model_dump() for a in stocks if a.symbol != normalized]
        )
        return {"removed": normalized}

    @app.get("/api/settings")
    async def settings():
        return {
            "settings": monitor.settings.model_dump(),
            "credentials": {service: monitor.vault.configured(service) for service in ["longport", "qq"]},
            "startup": startup.state(),
            "operators": [{"name": op.name, "description": op.description} for op in REGISTRY.values()],
        }

    @app.put("/api/settings")
    async def update_settings(value: Settings):
        monitor.update_settings(value)
        # Recalculate scores under the new versioned weights; no replayed notifications.
        for item in monitor.portfolio():
            await asyncio.to_thread(monitor.rebuild, item.symbol, True)
        return {"saved": True}

    @app.post("/api/credentials")
    async def credentials(value: Credentials):
        old = monitor.vault.load(value.service)
        updates = {k: v for k, v in value.model_dump().items() if k != "service" and v}
        merged = {**old, **updates}
        required = (
            {"app_key", "app_secret", "access_token"} if value.service == "longport" else {"app_secret"}
        )
        if not all(merged.get(k) for k in required):
            raise ValueError("凭据不完整；内容只需在本机填写，不要粘贴到聊天")
        monitor.vault.save(value.service, merged)
        if value.service == "qq":
            monitor.notifications.qq.access_token = ""
            monitor.notifications.qq.expires_at = 0
        monitor.reconnect_at = 0
        return {"configured": True, "service": value.service}

    class StartupRequest(BaseModel):
        enabled: bool

    @app.put("/api/startup")
    async def set_startup(value: StartupRequest):
        try:
            return startup.set_enabled(value.enabled)
        except OSError:
            raise HTTPException(400, "无法设置当前用户启动项，请检查系统权限") from None

    @app.post("/api/channels/qq/test")
    async def test_qq():
        envelope = NotificationEnvelope(
            event_id=str(uuid4()),
            symbol="TEST",
            timeframe="test",
            session="test",
            severity="info",
            title="QQ官方通道测试",
            message="本消息由你在本机点击测试发送，不包含持仓数据。",
            data_as_of=utcnow().isoformat(),
            source="test",
        )
        result = await monitor.notifications.qq.send(envelope)
        return {"status": result.status, "detail": result.detail}

    @app.get("/api/deliveries")
    async def deliveries():
        return monitor.store.deliveries()

    @app.get("/api/analysis/preview/{symbol}")
    async def preview(symbol: str):
        normalized = Allocation(symbol=symbol).symbol
        item = next((s for s in monitor.stocks() if s["symbol"] == normalized), None)
        if not item:
            raise HTTPException(404, "未找到股票")
        return safe_snapshot(item, monitor.settings.mode)

    @app.post("/api/analysis/{symbol}")
    async def analyze(symbol: str):
        normalized = Allocation(symbol=symbol).symbol
        item = next((s for s in monitor.stocks() if s["symbol"] == normalized), None)
        if not item:
            raise HTTPException(404, "未找到股票")
        job_id = await monitor.codex.request(item, monitor.settings.mode)
        return {"job_id": job_id, "status": "queued"}

    @app.websocket("/api/stream")
    async def stream(socket: WebSocket):
        if not local_origin(
            socket.headers.get("origin"), socket.headers.get("host")
        ) or not secrets.compare_digest(socket.cookies.get("signaldesk_session", ""), token):
            await socket.close(code=1008)
            return
        await socket.accept()
        try:
            while True:
                await socket.send_json(await monitor.snapshot())
                await asyncio.sleep(2)
        except (WebSocketDisconnect, RuntimeError):
            return

    frontend = Path(__file__).resolve().parent.parent / "frontend/dist"
    if (frontend / "assets").exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/{path:path}")
    async def index(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        if not (frontend / "index.html").exists():
            return JSONResponse({"detail": "请先在frontend运行npm ci和npm run build"}, status_code=503)
        return FileResponse(frontend / "index.html")

    return app
