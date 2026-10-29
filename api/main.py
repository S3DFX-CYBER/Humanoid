"""Humanoid API — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import get_settings
from api.database import close_pool, get_pool
from api.routes.jobs import router as jobs_router

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown: DB pool, Redis, and the arq queue pool."""
    settings = get_settings()

    await get_pool()

    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    # One shared arq pool for the process instead of one per request.
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    try:
        yield
    finally:
        await app.state.arq.aclose()
        await app.state.redis.aclose()
        await close_pool()


app = FastAPI(
    title="Humanoid API",
    description="AI research and drafting assistant for academic work",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the traceback and return a stable error envelope to the client."""
    logger.exception("[api] unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "path": request.url.path},
    )


@app.get("/health")
async def health():
    """Liveness — the process is up."""
    return {"status": "ok", "service": "humanoid-api"}


@app.get("/readyz")
async def readyz():
    """Readiness — dependencies this process needs are reachable."""
    checks: dict[str, str] = {}

    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    try:
        await app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "checks": checks},
    )
