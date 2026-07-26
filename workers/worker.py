"""arq worker — async job pipeline executor.

Picks up jobs from the Redis queue, transitions them through stages,
and persists state after every stage so a crashed worker can resume
rather than restart.

Phase 0: Only proves the loop works with `queued → researching → done`.
"""

import asyncio
import logging
import uuid

import asyncpg

from arq.connections import RedisSettings

from api.config import get_settings
from providers import get_provider_pool
from workers.stages import (
    run_research,
    run_outline,
    run_draft,
    run_verify,
    run_style,
    run_format,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Ordered list of pipeline stages and their handlers
PIPELINE_STAGES = [
    ("researching", run_research),
    ("outlining", run_outline),
    ("drafting", run_draft),
    ("verifying", run_verify),
    ("styling", run_style),
    ("formatting", run_format),
]


async def _get_db_pool(ctx: dict) -> asyncpg.Pool:
    """Get or create the DB connection pool from the worker context."""
    if "db_pool" not in ctx:
        settings = get_settings()
        ctx["db_pool"] = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=1,
            max_size=5,
        )
    return ctx["db_pool"]


async def _update_job_status(pool: asyncpg.Pool, job_id: str, status: str) -> None:
    """Update the job's status in the database."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET status = $1, updated_at = now() WHERE id = $2",
            status,
            uuid.UUID(job_id),
        )
    logger.info("[worker] job=%s status → %s", job_id, status)


async def _create_stage_record(
    pool: asyncpg.Pool,
    job_id: str,
    stage_name: str,
) -> str:
    """Create a job_stages row and return its ID."""
    stage_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO job_stages (id, job_id, stage_name, status, started_at)
            VALUES ($1, $2, $3, 'running', now())
            """,
            stage_id,
            uuid.UUID(job_id),
            stage_name,
        )
    return str(stage_id)


async def _complete_stage(
    pool: asyncpg.Pool,
    stage_id: str,
    output_data: dict,
) -> None:
    """Mark a stage as completed with its output."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE job_stages
            SET status = 'completed', output_data = $1, completed_at = now()
            WHERE id = $2
            """,
            output_data,
            uuid.UUID(stage_id),
        )


async def _fail_stage(
    pool: asyncpg.Pool,
    stage_id: str,
    error: str,
) -> None:
    """Mark a stage as failed with error details."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE job_stages
            SET status = 'failed', error = $1, completed_at = now()
            WHERE id = $2
            """,
            error,
            uuid.UUID(stage_id),
        )


async def _get_last_completed_stage(pool: asyncpg.Pool, job_id: str) -> str | None:
    """Find the last completed stage name for resume support."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT stage_name FROM job_stages
            WHERE job_id = $1 AND status = 'completed'
            ORDER BY completed_at DESC
            LIMIT 1
            """,
            uuid.UUID(job_id),
        )
    return row["stage_name"] if row else None


async def run_pipeline(ctx: dict, job_id: str) -> str:
    """Execute the full pipeline for a job.

    Supports resume: if the worker crashes mid-pipeline, the next
    pickup will find the last completed stage and continue from there.
    """
    pool = await _get_db_pool(ctx)
    logger.info("[worker] Starting pipeline for job=%s", job_id)

    try:
        # Determine where to resume from (if any)
        last_completed = await _get_last_completed_stage(pool, job_id)

        # Find the starting index
        start_idx = 0
        if last_completed:
            for i, (stage_name, _) in enumerate(PIPELINE_STAGES):
                if stage_name == last_completed:
                    start_idx = i + 1
                    break
            logger.info(
                "[worker] job=%s resuming after stage '%s' (index %d)",
                job_id,
                last_completed,
                start_idx,
            )

        # Execute stages sequentially
        for i in range(start_idx, len(PIPELINE_STAGES)):
            stage_name, stage_handler = PIPELINE_STAGES[i]

            # Update job status to current stage
            await _update_job_status(pool, job_id, stage_name)

            # Create stage record
            stage_id = await _create_stage_record(pool, job_id, stage_name)

            try:
                # Run stage handler with provider and database components.
                output = await stage_handler(
                    job_id,
                    {"provider_pool": ctx["provider_pool"], "db_pool": pool},
                )

                # Persist output
                await _complete_stage(pool, stage_id, output)
                logger.info("[worker] job=%s stage '%s' completed", job_id, stage_name)

                # Small delay between stages (simulates real work in Phase 0)
                await asyncio.sleep(1)

            except Exception as stage_error:
                await _fail_stage(pool, stage_id, str(stage_error))
                await _update_job_status(pool, job_id, "failed")
                logger.error(
                    "[worker] job=%s stage '%s' failed: %s",
                    job_id,
                    stage_name,
                    stage_error,
                )
                raise

        # All stages done
        await _update_job_status(pool, job_id, "done")
        logger.info("[worker] job=%s pipeline completed successfully", job_id)
        return "done"

    except Exception as e:
        logger.error("[worker] job=%s pipeline failed: %s", job_id, e)
        await _update_job_status(pool, job_id, "failed")
        raise


async def startup(ctx: dict) -> None:
    """Worker startup hook — initialize shared resources."""
    logger.info("[worker] Starting up...")
    await _get_db_pool(ctx)
    ctx["provider_pool"] = get_provider_pool()


async def shutdown(ctx: dict) -> None:
    """Worker shutdown hook — clean up shared resources."""
    logger.info("[worker] Shutting down...")
    if "db_pool" in ctx:
        await ctx["db_pool"].close()


class WorkerSettings:
    """arq worker configuration."""

    functions = [run_pipeline]
    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

    # Worker tuning
    max_jobs = 5
    job_timeout = 600  # 10 min timeout per job
    retry_jobs = True
    max_tries = 3
