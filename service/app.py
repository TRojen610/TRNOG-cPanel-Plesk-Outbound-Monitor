from __future__ import annotations

import argparse
import json
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Empty

import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import ServiceConfig, load_config
from .runtime import ServiceRuntime
from .store import EventQuery

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES = Jinja2Templates(directory=str(ROOT_DIR / "web" / "templates"))


def _base_path(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-prefix", "").strip()
    if forwarded:
        return forwarded if forwarded.endswith("/") else f"{forwarded}/"
    return "/"


def _build_query(
    window_seconds: int,
    user: str,
    dst_ip: str,
    port: int | None,
    family: str,
    search: str,
) -> EventQuery:
    return EventQuery(
        window_seconds=window_seconds,
        user=user,
        dst_ip=dst_ip,
        port=port,
        family=family,
        search=search,
    )


def create_app(config: ServiceConfig | None = None) -> FastAPI:
    config = config or load_config()
    runtime = ServiceRuntime(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        runtime.start()
        yield
        runtime.stop()

    app = FastAPI(title="TRNOG Outbound Monitor", lifespan=lifespan)
    app.state.config = config
    app.state.runtime = runtime
    app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "web" / "static")), name="static")

    @app.middleware("http")
    async def localhost_guard(request: Request, call_next):
        if config.http.localhost_only:
            client_host = request.client.host if request.client else ""
            if client_host not in {"127.0.0.1", "::1", "localhost"}:
                return JSONResponse(
                    {"error": "remote access disabled by configuration"},
                    status_code=403,
                )
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return TEMPLATES.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "title": "TRNOG Outbound Monitor",
                "base_path": _base_path(request),
                "embed": False,
                "default_window_seconds": config.ui.default_window_seconds,
                "fallback_poll_seconds": config.ui.fallback_poll_seconds,
            },
        )

    @app.get("/embed/whm", response_class=HTMLResponse)
    async def dashboard_embed(request: Request):
        return TEMPLATES.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "title": "TRNOG Outbound Monitor",
                "base_path": _base_path(request),
                "embed": True,
                "default_window_seconds": config.ui.default_window_seconds,
                "fallback_poll_seconds": config.ui.fallback_poll_seconds,
            },
        )

    @app.get("/health")
    async def health():
        return runtime.health()

    @app.get("/api/summary")
    async def summary(
        window_seconds: int = Query(default=config.ui.default_window_seconds, ge=60, le=604800),
        user: str = "",
        dst_ip: str = "",
        port: int | None = Query(default=None, ge=1, le=65535),
        family: str = "",
        search: str = "",
    ):
        query = _build_query(window_seconds, user, dst_ip, port, family, search)
        return runtime.store.summary(query)

    @app.get("/api/events")
    async def events(
        window_seconds: int = Query(default=config.ui.default_window_seconds, ge=60, le=604800),
        user: str = "",
        dst_ip: str = "",
        port: int | None = Query(default=None, ge=1, le=65535),
        family: str = "",
        search: str = "",
        limit: int = Query(default=config.ui.events_limit, ge=1, le=1000),
    ):
        query = _build_query(window_seconds, user, dst_ip, port, family, search)
        items = [event.to_dict() for event in runtime.store.events(query, limit)]
        return {"items": items, "count": len(items)}

    @app.get("/api/top/destinations")
    async def top_destinations(
        window_seconds: int = Query(default=config.ui.default_window_seconds, ge=60, le=604800),
        user: str = "",
        dst_ip: str = "",
        port: int | None = Query(default=None, ge=1, le=65535),
        family: str = "",
        search: str = "",
        limit: int = Query(default=8, ge=1, le=50),
    ):
        query = _build_query(window_seconds, user, dst_ip, port, family, search)
        return {"items": runtime.store.top_destinations(query, limit)}

    @app.get("/api/top/users")
    async def top_users(
        window_seconds: int = Query(default=config.ui.default_window_seconds, ge=60, le=604800),
        user: str = "",
        dst_ip: str = "",
        port: int | None = Query(default=None, ge=1, le=65535),
        family: str = "",
        search: str = "",
        limit: int = Query(default=8, ge=1, le=50),
    ):
        query = _build_query(window_seconds, user, dst_ip, port, family, search)
        return {"items": runtime.store.top_users(query, limit)}

    @app.get("/api/top/ports")
    async def top_ports(
        window_seconds: int = Query(default=config.ui.default_window_seconds, ge=60, le=604800),
        user: str = "",
        dst_ip: str = "",
        port: int | None = Query(default=None, ge=1, le=65535),
        family: str = "",
        search: str = "",
        limit: int = Query(default=8, ge=1, le=50),
    ):
        query = _build_query(window_seconds, user, dst_ip, port, family, search)
        return {"items": runtime.store.top_ports(query, limit)}

    @app.get("/events/stream")
    async def event_stream():
        queue = runtime.broadcaster.subscribe()

        def generate():
            try:
                yield "retry: 5000\n\n"
                while True:
                    try:
                        payload = queue.get(timeout=15)
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    except Empty:
                        yield ": keepalive\n\n"
            finally:
                runtime.broadcaster.unsubscribe(queue)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TRNOG Outbound Monitor service")
    parser.add_argument("--config", dest="config_path", default=None)
    args = parser.parse_args(argv)
    config = load_config(args.config_path)
    app = create_app(config)
    uvicorn.run(app, host=config.http.host, port=config.http.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
