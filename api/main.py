"""Humanoid API — FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis

from api.config import get_settings
from api.database import get_pool, close_pool
from api.routes.jobs import router as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown: DB pool + Redis connection."""
    settings = get_settings()

    # Initialize DB pool
    await get_pool()

    # Initialize Redis
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    yield

    # Cleanup
    await app.state.redis.aclose()
    await close_pool()


app = FastAPI(
    title="Humanoid API",
    description="AI research and drafting assistant for academic work",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "humanoid-api"}
