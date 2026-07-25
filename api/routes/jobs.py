"""Job management routes — create, query, and track pipeline jobs."""

import uuid
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel

from api.database import fetch_one, fetch_all
from arq.connections import create_pool, RedisSettings
from api.config import get_settings
from api.dependencies import get_current_user

router = APIRouter()


# ── Request / Response Models ────────────────────────────────

class JobCreate(BaseModel):
    topic: str
    citation_style: str = "apa"
    config: dict = {}


class JobResponse(BaseModel):
    id: str
    user_id: str
    topic: str
    status: str
    citation_style: str
    config: dict
    created_at: str
    updated_at: str


class StageResponse(BaseModel):
    id: str
    job_id: str
    stage_name: str
    status: str
    input_data: dict
    output_data: dict
    error: str | None
    started_at: str | None
    completed_at: str | None


# ── Helpers ──────────────────────────────────────────────────

def _record_to_dict(record) -> dict:
    """Convert an asyncpg Record to a JSON-safe dict."""
    d = dict(record)
    for key, val in d.items():
        if isinstance(val, uuid.UUID):
            d[key] = str(val)
        elif hasattr(val, "isoformat"):
            d[key] = val.isoformat()
    return d


# ── Routes ───────────────────────────────────────────────────

@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: JobCreate,
    request: Request,
    user_id: str = Depends(get_current_user),
):
    """Create a new job and enqueue it for the arq worker."""
    job_id = uuid.uuid4()

    row = await fetch_one(
        """
        INSERT INTO jobs (id, user_id, topic, status, citation_style, config)
        VALUES ($1, $2, $3, 'queued', $4, $5)
        RETURNING *
        """,
        job_id,
        uuid.UUID(user_id),
        body.topic,
        body.citation_style,
        body.config,
    )

    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create job")

    # Enqueue to arq
    settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    redis_pool = await create_pool(redis_settings)
    await redis_pool.enqueue_job("run_pipeline", str(job_id))
    await redis_pool.aclose()

    return JobResponse(**_record_to_dict(row))


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, current_user: str = Depends(get_current_user)):
    """Fetch a single job by ID."""
    row = await fetch_one(
        "SELECT * FROM jobs WHERE id = $1 AND user_id = $2",
        uuid.UUID(job_id),
        uuid.UUID(current_user),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**_record_to_dict(row))


@router.get("/{job_id}/stages", response_model=list[StageResponse])
async def get_job_stages(job_id: str, current_user: str = Depends(get_current_user)):
    """Fetch all stages for a job, ordered by creation time."""
    # First verify the job belongs to the current user
    job = await fetch_one(
        "SELECT id FROM jobs WHERE id = $1 AND user_id = $2",
        uuid.UUID(job_id),
        uuid.UUID(current_user),
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    rows = await fetch_all(
        """
        SELECT * FROM job_stages
        WHERE job_id = $1
        ORDER BY started_at ASC NULLS LAST
        """,
        uuid.UUID(job_id),
    )
    return [StageResponse(**_record_to_dict(r)) for r in rows]
