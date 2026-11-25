from __future__ import annotations

import asyncio
import hashlib
import json
import math
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import startup
from .broker_oauth import CALLBACK, FLOW_SECONDS
from .models import (
    AgentProviderId,
    Allocation,
    AnalyzeRequest,
    Credentials,
    NotificationEnvelope,
    Settings,
    utcnow,
)
from .operators import REGISTRY
from .security import data_directory, safe_snapshot, session_token
from .service import Monitor
from .storage import Store


def local_origin(origin: str | None, host: str | None) -> bool:
    if not origin:
        return True
    parsed = urlparse(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc == host


def _sanitize_json(value):
    """递归清理意外的 NaN / Inf 浮点值，避免浏览器 JSON.parse 异常或渲染崩溃。"""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(v) for v in value]
    return value


def _snapshot_fingerprint(payload: dict) -> str:
    """计算快照业务指纹（忽略每秒跳动的时钟字段），避免静止状态下重复推送大包。"""
    stable = {k: v for k, v in payload.items() if k not in {"now", "market"}}
    market = payload.get("market") or {}
    stable["market_state"] = (
        market.get("session"),
        market.get("label"),
        market.get("early_close"),
    )
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()


class FavoriteRequest(BaseModel):
    favorite: bool


class StartupRequest(BaseModel):
    enabled: bool


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
        if request.url.path.startswith("/api/") or request.url.path == CALLBACK:
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
        response = JSONResponse(_sanitize_json(await monitor.snapshot()))
        response.set_cookie("signaldesk_session", token, httponly=True, samesite="strict")
        return response

    @app.get("/api/dashboard")
    async def dashboard():
        return _sanitize_json(await monitor.snapshot())

    @app.get("/api/macro")
    async def macro_regime():
        return _sanitize_json(monitor.macro_regime())

    @app.get("/api/stock/{symbol}")
    async def stock(symbol: str, timeframe: str = "day", session: str = "regular"):
        if timeframe not in {"15m", "day"} or session not in {"regular", "pre", "post", "overnight"}:
            raise HTTPException(400, "不支持的周期或时段")
        normalized = Allocation(symbol=symbol).symbol
        return _sanitize_json(
            monitor.detail_for(normalized, timeframe, "regular" if timeframe == "day" else session)
        )

    @app.get("/api/stock/{symbol}/live-eval")
    async def stock_live_eval(symbol: str):
        normalized = Allocation(symbol=symbol).symbol
        return _sanitize_json(monitor.live_evaluation_for(normalized))

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
        if item and item.in_watchlist:
            raise ValueError("该股票来自账号自选股单，请在长桥 App 移出自选；或取消本地收藏")
        monitor.store.set(
            f"portfolio:{monitor.settings.mode}", [a.model_dump() for a in stocks if a.symbol != normalized]
        )
        return {"removed": normalized}

    @app.put("/api/favorites/{symbol}")
    async def favorite_stock(symbol: str, value: FavoriteRequest):
        normalized = Allocation(symbol=symbol).symbol
        saved = monitor.set_favorite(normalized, value.favorite)
        return {"symbol": normalized, "favorite": saved.favorite}

    @app.post("/api/watchlist/sync")
    async def sync_watchlist():
        return await monitor.sync_watchlist_now()

    @app.get("/api/settings")
    async def settings():
        return {
            "settings": monitor.settings.model_dump(),
            "credentials": {service: monitor.vault.configured(service) for service in ["longport", "qq"]},
            "broker_platform": monitor.vault.load("longport").get("platform", "longport"),
            "broker_auth": monitor.oauth.status(),
            "startup": startup.state(),
            "operators": [op.metadata() for op in REGISTRY.values()],
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
        async with monitor.oauth.lock:
            old = monitor.vault.load(value.service)
            if old.get("method") == "oauth":
                old = {}
            updates = {k: v for k, v in value.model_dump().items() if k != "service" and v}
            merged = {**old, **updates}
            required = (
                {"app_key", "app_secret", "access_token"} if value.service == "longport" else {"app_secret"}
            )
            if not all(merged.get(k) for k in required):
                raise ValueError("凭据不完整，请在本机填写。")
            monitor.vault.save(value.service, merged)
            if value.service == "longport":
                monitor.oauth.pending, monitor.oauth.message = None, ""
        if value.service == "qq":
            monitor.notifications.qq.access_token = ""
            monitor.notifications.qq.expires_at = 0
        elif monitor.settings.mode == "live":
            monitor.active_mode = None  # Use the saved gateway and credentials on the next connection.
        monitor.reconnect_at = 0
        return {"configured": True, "service": value.service}

    @app.post("/api/broker/oauth/start")
    async def start_oauth(request: Request):
        if request.url.hostname not in {"localhost", "127.0.0.1"}:
            raise HTTPException(400, "请从本机地址打开看板后授权。")
        redirect_uri = str(request.url.replace(path=CALLBACK, query=""))
        url, browser = await monitor.oauth.start(redirect_uri)
        response = JSONResponse({"url": url})
        response.set_cookie(
            "broker_login", browser, max_age=FLOW_SECONDS, path=CALLBACK, httponly=True, samesite="lax"
        )
        return response

    @app.get("/api/broker/oauth/status")
    async def oauth_status():
        return monitor.oauth.status()

    @app.get(CALLBACK)
    async def broker_callback(request: Request):
        query = request.query_params
        result = await monitor.oauth.finish(
            query.get("state", ""),
            request.cookies.get("broker_login", ""),
            query.get("code", ""),
            "error" in query,
        )
        if result == "success" and monitor.settings.mode == "live":
            monitor.active_mode = None
            monitor.reconnect_at = 0
        response = RedirectResponse(f"/?broker-result={result}", status_code=303)
        if result != "invalid":
            response.delete_cookie("broker_login", path=CALLBACK)
        return response

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
        macro = monitor.macro_regime()
        item = next((s for s in monitor.stocks(macro=macro) if s["symbol"] == normalized), None)
        if not item:
            raise HTTPException(404, "未找到股票")
        return safe_snapshot(item, monitor.settings.mode, macro, monitor.gold_snapshot(macro=macro))

    @app.post("/api/analysis/{symbol}")
    async def analyze(
        symbol: str,
        request: Request,
        agent: AgentProviderId | None = None,
    ):
        normalized = Allocation(symbol=symbol).symbol
        macro = monitor.macro_regime()
        item = next((s for s in monitor.stocks(macro=macro) if s["symbol"] == normalized), None)
        if not item:
            raise HTTPException(404, "未找到股票")
        chosen_agent: AgentProviderId | None = agent
        raw_body = (await request.body()).strip()
        if raw_body:
            try:
                parsed = AnalyzeRequest.model_validate_json(raw_body)
            except Exception as exc:
                raise HTTPException(422, f"请求参数不合法：{exc}") from None
            if parsed.agent is not None:
                chosen_agent = parsed.agent
        job_id, resolved_agent = await monitor.agents.request(
            item,
            monitor.settings.mode,
            agent=chosen_agent,
            macro=macro,
            gold=monitor.gold_snapshot(macro=macro),
        )
        return {"job_id": job_id, "agent": resolved_agent, "status": "queued"}

    @app.websocket("/api/stream")
    async def stream(socket: WebSocket):
        if not local_origin(
            socket.headers.get("origin"), socket.headers.get("host")
        ) or not secrets.compare_digest(socket.cookies.get("signaldesk_session", ""), token):
            await socket.close(code=1008)
            return
        await socket.accept()
        last_digest = ""
        last_sent = 0.0
        try:
            while True:
                payload = _sanitize_json(await monitor.snapshot())
                digest = _snapshot_fingerprint(payload)
                now_mono = time.monotonic()
                # 仅在业务数据变化或心跳超过20秒时推送，避免休市/静止时每2秒灌入数百KB重复JSON
                if digest != last_digest or (now_mono - last_sent) >= 20.0:
                    text = json.dumps(payload, ensure_ascii=False, allow_nan=False)
                    await socket.send_text(text)
                    last_digest = digest
                    last_sent = now_mono
                await asyncio.sleep(2)
        except (WebSocketDisconnect, RuntimeError):
            return

    frontend = Path(__file__).resolve().parent.parent / "frontend/dist"
    if (frontend / "assets").exists():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    # 网页标签图标静态白名单，避免浏览器请求 /favicon.* 被 SPA 兜底成 index.html
    icon_files = {
        "favicon.svg": "image/svg+xml",
        "favicon.ico": "image/x-icon",
        "apple-touch-icon.png": "image/png",
    }

    @app.get("/{path:path}")
    async def index(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        if path in icon_files:
            icon_path = frontend / path
            if not icon_path.exists():
                raise HTTPException(404, "图标资源不存在")
            return FileResponse(
                icon_path,
                media_type=icon_files[path],
                headers={"Cache-Control": "public, max-age=86400"},
            )
        if not (frontend / "index.html").exists():
            return JSONResponse({"detail": "请先在frontend运行npm ci和npm run build"}, status_code=503)
        return FileResponse(
            frontend / "index.html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    return app
