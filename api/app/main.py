import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.config import Settings, get_settings
from app.db import Database

log = logging.getLogger("filinglens")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.database_url) if settings.database_url else None
        if db is None:
            log.warning("FILINGLENS_DATABASE_URL is not set; the API will report not ready")
        else:
            await db.open()
        app.state.db = db
        try:
            yield
        finally:
            if db is not None:
                await db.close()

    app = FastAPI(
        title="FilingLens API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Liveness: the process is up. Never touches the database."""
        return {"status": "ok", "version": __version__}

    @app.get("/api/health/ready")
    async def ready(request: Request) -> JSONResponse:
        """Readiness: the database answers and pgvector is enabled."""
        db: Database | None = request.app.state.db
        if db is None:
            return _unavailable("not configured")
        try:
            version = await db.pgvector_version()
        except Exception:
            log.exception("readiness check failed")
            return _unavailable("unreachable")
        if version is None:
            return _unavailable("pgvector missing")
        return JSONResponse({"status": "ready", "database": "ok", "pgvector": version})

    return app


def _unavailable(reason: str) -> JSONResponse:
    return JSONResponse(status_code=503, content={"status": "unavailable", "database": reason})


app = create_app()
