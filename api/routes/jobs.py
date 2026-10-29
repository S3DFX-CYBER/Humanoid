"""Job management routes — create, list, query, and track pipeline jobs."""

import logging
import uuid
from datetime import datetime
from typing import Any, Literal

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from api.config import get_settings
from api.database import fetch_all, fetch_one
from api.dependencies import get_current_user

router = APIRouter()

logger = logging.getLogger(__name__)


def get_arq_pool(request: Request) -> ArqRedis:
    """Dependency: the shared arq pool created during app startup."""
    return request.app.state.arq


# ── Constants ────────────────────────────────────────────────

CitationStyle = Literal["apa", "mla", "chicago", "ieee"]

ACTIVE_STATUSES = (
    "queued",
    "researching",
    "outlining",
    "outline_pending_approval",
    "drafting",
    "verifying",
    "styling",
    "formatting",
)


# ── Request / Response Models ────────────────────────────────


class JobCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    citation_style: CitationStyle = "apa"
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def _strip_topic(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("topic must be at least 3 characters")
        return stripped


class JobResponse(BaseModel):
    id: str
    user_id: str
    topic: str
    status: str
    citation_style: str
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class StageResponse(BaseModel):
    id: str
    job_id: str
    stage_name: str
    status: str
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class DocumentResponse(BaseModel):
    job_id: str
    has_docx: bool
    markdown: str | None = None
    filename: str | None = None
    byte_size: int | None = None


# ── Helpers ──────────────────────────────────────────────────


def _record_to_dict(record) -> dict:
    """Convert an asyncpg Record to a JSON-safe dict."""
    d = dict(record)
    for key, val in d.items():
        if isinstance(val, uuid.UUID):
            d[key] = str(val)
    return d


def _parse_uuid(value: str) -> uuid.UUID:
    """Parse a path UUID, returning 404 rather than a 500 on malformed input."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


async def _load_owned_job(job_id: str, user_id: str) -> dict:
    """Fetch a job the caller owns, or 404."""
    row = await fetch_one(
        "SELECT * FROM jobs WHERE id = $1 AND user_id = $2",
        _parse_uuid(job_id),
        uuid.UUID(user_id),
        user_id=user_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _record_to_dict(row)


# ── Routes ───────────────────────────────────────────────────


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    body: JobCreate,
    user_id: str = Depends(get_current_user),
    arq: ArqRedis = Depends(get_arq_pool),
):
    """Create a new job and enqueue it for the arq worker."""
    settings = get_settings()

    active_jobs = await fetch_one(
        """
        SELECT COUNT(*) AS count FROM jobs
        WHERE user_id = $1 AND status::text = ANY($2::text[])
        """,
        uuid.UUID(user_id),
        list(ACTIVE_STATUSES),
        user_id=user_id,
    )
    if active_jobs and active_jobs["count"] >= settings.max_concurrent_jobs_per_user:
        raise HTTPException(
            status_code=429,
            detail=(
                "You already have "
                f"{active_jobs['count']} jobs running "
                f"(limit {settings.max_concurrent_jobs_per_user}). "
                "Wait for one to finish before starting another."
            ),
        )

    daily_jobs = await fetch_one(
        """
        SELECT COUNT(*) AS count FROM jobs
        WHERE user_id = $1 AND created_at > now() - interval '1 day'
        """,
        uuid.UUID(user_id),
        user_id=user_id,
    )
    if daily_jobs and daily_jobs["count"] >= settings.max_daily_jobs_per_user:
        raise HTTPException(
            status_code=429,
            detail=(
                "Daily job limit reached "
                f"({settings.max_daily_jobs_per_user}). Try again tomorrow."
            ),
        )

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
        user_id=user_id,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create job")

    # user_id travels with the payload so the worker can set its RLS context.
    try:
        await arq.enqueue_job("run_pipeline", str(job_id), user_id)
    except Exception as exc:
        # A job stuck in 'queued' with no worker is worse than an honest error.
        logger.exception("[jobs] could not enqueue job %s", job_id)
        await fetch_one(
            """
            UPDATE jobs SET status = 'failed', updated_at = now()
            WHERE id = $1 AND user_id = $2
            RETURNING id
            """,
            job_id,
            uuid.UUID(user_id),
            user_id=user_id,
        )
        raise HTTPException(
            status_code=503,
            detail="The job queue is unavailable. Nothing was charged — try again.",
        ) from exc

    return JobResponse(**_record_to_dict(row))


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    user_id: str = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List the caller's jobs, newest first."""
    rows = await fetch_all(
        """
        SELECT * FROM jobs
        WHERE user_id = $1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        uuid.UUID(user_id),
        limit,
        offset,
        user_id=user_id,
    )
    return [JobResponse(**_record_to_dict(r)) for r in rows]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, user_id: str = Depends(get_current_user)):
    """Fetch a single job by ID."""
    return JobResponse(**await _load_owned_job(job_id, user_id))


@router.get("/{job_id}/stages", response_model=list[StageResponse])
async def get_job_stages(job_id: str, user_id: str = Depends(get_current_user)):
    """Fetch all stages for a job, in pipeline order."""
    await _load_owned_job(job_id, user_id)

    rows = await fetch_all(
        """
        SELECT * FROM job_stages
        WHERE job_id = $1
        ORDER BY started_at ASC NULLS LAST, stage_name ASC
        """,
        _parse_uuid(job_id),
        user_id=user_id,
    )
    return [StageResponse(**_record_to_dict(r)) for r in rows]


@router.get("/{job_id}/document", response_model=DocumentResponse)
async def get_job_document(job_id: str, user_id: str = Depends(get_current_user)):
    """Describe the finished document: DOCX availability plus the Markdown body."""
    job = await _load_owned_job(job_id, user_id)

    format_row = await fetch_one(
        """
        SELECT output_data FROM job_stages
        WHERE job_id = $1 AND stage_name = 'formatting' AND status = 'completed'
        ORDER BY completed_at DESC
        LIMIT 1
        """,
        _parse_uuid(job_id),
        user_id=user_id,
    )
    markdown = None
    if format_row and isinstance(format_row["output_data"], dict):
        markdown = format_row["output_data"].get("markdown")

    doc = await fetch_one(
        """
        SELECT filename, byte_size FROM documents
        WHERE job_id = $1 AND kind = 'docx'
        LIMIT 1
        """,
        _parse_uuid(job_id),
        user_id=user_id,
    )

    return DocumentResponse(
        job_id=job["id"],
        has_docx=doc is not None,
        markdown=markdown,
        filename=doc["filename"] if doc else None,
        byte_size=doc["byte_size"] if doc else None,
    )


@router.get("/{job_id}/document/file")
async def download_job_document(job_id: str, user_id: str = Depends(get_current_user)):
    """Download the rendered DOCX (or the Markdown body as a fallback)."""
    await _load_owned_job(job_id, user_id)

    doc = await fetch_one(
        """
        SELECT filename, mime_type, content FROM documents
        WHERE job_id = $1 AND kind = 'docx'
        LIMIT 1
        """,
        _parse_uuid(job_id),
        user_id=user_id,
    )
    if doc is not None:
        return Response(
            content=doc["content"],
            media_type=doc["mime_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{doc["filename"]}"'
            },
        )

    format_row = await fetch_one(
        """
        SELECT output_data FROM job_stages
        WHERE job_id = $1 AND stage_name = 'formatting' AND status = 'completed'
        ORDER BY completed_at DESC
        LIMIT 1
        """,
        _parse_uuid(job_id),
        user_id=user_id,
    )
    markdown = None
    if format_row and isinstance(format_row["output_data"], dict):
        markdown = format_row["output_data"].get("markdown")

    if not markdown:
        raise HTTPException(status_code=404, detail="Document not ready")

    filename = f"humanoid_{job_id[:8]}.md"
    return Response(
        content=markdown.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{job_id}/retry", response_model=JobResponse, status_code=202)
async def retry_job(
    job_id: str,
    user_id: str = Depends(get_current_user),
    arq: ArqRedis = Depends(get_arq_pool),
):
    """Re-enqueue a failed job. Completed stages are kept and skipped."""
    job = await _load_owned_job(job_id, user_id)

    if job["status"] not in ("failed", "done"):
        raise HTTPException(
            status_code=409,
            detail="Job is still running — wait for it to finish first.",
        )

    await fetch_one(
        """
        UPDATE jobs SET status = 'queued', updated_at = now()
        WHERE id = $1 AND user_id = $2
        RETURNING id
        """,
        _parse_uuid(job_id),
        uuid.UUID(user_id),
        user_id=user_id,
    )
    await arq.enqueue_job("run_pipeline", job_id, user_id, True)
    return JobResponse(**await _load_owned_job(job_id, user_id))
