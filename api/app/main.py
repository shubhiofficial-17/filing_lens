import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.config import Settings, get_settings
from app.container import Container, build_container
from app.routes import router

log = logging.getLogger("filinglens")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = await run_in_threadpool(build_container, settings)
        app.state.container = container
        try:
            yield
        finally:
            await run_in_threadpool(container.close)

    app = FastAPI(
        title="FilingLens API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """Liveness: the process is up. Never touches the database."""
        return {"status": "ok", "version": __version__}

    @app.get("/api/health/ready")
    def ready() -> JSONResponse:
        """Readiness: Postgres answers and pgvector is enabled."""
        container: Container = app.state.container
        if not container.persistent:
            return _unavailable("not configured")
        try:
            version = container.store.pgvector_version()  # type: ignore[attr-defined]
        except Exception:
            log.exception("readiness check failed")
            return _unavailable("unreachable")
        if version is None:
            return _unavailable("pgvector missing")
        return JSONResponse({"status": "ready", "database": "ok", "pgvector": version})

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - started) * 1000
        if request.url.path not in ("/api/health", "/api/health/ready"):
            log.info("%s %s %d %.0fms", request.method, request.url.path, response.status_code, ms)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.include_router(router)
    return app


def _unavailable(reason: str) -> JSONResponse:
    return JSONResponse(status_code=503, content={"status": "unavailable", "database": reason})


app = create_app()
