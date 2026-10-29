"""arq worker — async job pipeline executor.

Picks jobs off the Redis queue, walks them through the stages in
``workers.pipeline``, and persists state after every stage so a crashed
worker resumes instead of restarting.

Every database write runs with the job owner's RLS context set, so the
worker needs no elevated database privileges.
"""

import logging
import uuid

import asyncpg
from arq.connections import RedisSettings

from api.config import get_settings
from api.database import init_connection, user_connection
from providers import get_provider_pool
from workers.pipeline import (
    PIPELINE_STAGES,
    STAGE_ORDER,
    next_stage_index,
)
from workers.stages import (
    run_draft,
    run_format,
    run_outline,
    run_research,
    run_style,
    run_verify,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

STAGE_HANDLERS = {
    "research": run_research,
    "outline": run_outline,
    "draft": run_draft,
    "verify": run_verify,
    "style": run_style,
    "format": run_format,
}


async def _get_db_pool(ctx: dict) -> asyncpg.Pool:
    """Get or create the DB connection pool from the worker context."""
    if "db_pool" not in ctx:
        settings = get_settings()
        ctx["db_pool"] = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=1,
            max_size=5,
            init=init_connection,
            command_timeout=60,
        )
    return ctx["db_pool"]


async def _set_status(pool, job_id: str, user_id: str, status: str) -> None:
    async with user_connection(pool, user_id) as conn:
        await conn.execute(
            "UPDATE jobs SET status = $1::job_status WHERE id = $2",
            status,
            uuid.UUID(job_id),
        )
    logger.info("[worker] job=%s status -> %s", job_id, status)


async def _create_stage(pool, job_id: str, user_id: str, stage_name: str) -> str:
    stage_id = uuid.uuid4()
    async with user_connection(pool, user_id) as conn:
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


async def _complete_stage(pool, stage_id: str, user_id: str, output: dict) -> None:
    async with user_connection(pool, user_id) as conn:
        await conn.execute(
            """
            UPDATE job_stages
            SET status = 'completed', output_data = $1, completed_at = now()
            WHERE id = $2
            """,
            output,
            uuid.UUID(stage_id),
        )


async def _fail_stage(pool, stage_id: str, user_id: str, error: str) -> None:
    async with user_connection(pool, user_id) as conn:
        await conn.execute(
            """
            UPDATE job_stages
            SET status = 'failed', error = $1, completed_at = now()
            WHERE id = $2
            """,
            error[:4000],
            uuid.UUID(stage_id),
        )


async def _reset_stale_stages(pool, job_id: str, user_id: str) -> None:
    """Mark stages left 'running' by a crashed worker as failed.

    Without this a resumed pipeline shows a stage stuck at "running" forever.
    """
    async with user_connection(pool, user_id) as conn:
        await conn.execute(
            """
            UPDATE job_stages
            SET status = 'failed',
                error = COALESCE(error, 'Interrupted: worker restarted'),
                completed_at = now()
            WHERE job_id = $1 AND status = 'running'
            """,
            uuid.UUID(job_id),
        )


async def _last_completed_stage(pool, job_id: str, user_id: str) -> str | None:
    """Return the furthest completed stage in pipeline order."""
    async with user_connection(pool, user_id) as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT stage_name FROM job_stages
            WHERE job_id = $1 AND status = 'completed'
            """,
            uuid.UUID(job_id),
        )
    completed = {row["stage_name"] for row in rows}
    best_index = -1
    best_stage = None
    for index, stage_name in enumerate(STAGE_ORDER):
        if stage_name in completed and index > best_index:
            best_index = index
            best_stage = stage_name
    return best_stage


async def _clear_stages(pool, job_id: str, user_id: str) -> None:
    """Wipe stage and document history for an explicit retry-from-scratch."""
    async with user_connection(pool, user_id) as conn:
        await conn.execute(
            "DELETE FROM job_stages WHERE job_id = $1", uuid.UUID(job_id)
        )
        await conn.execute(
            "DELETE FROM documents WHERE job_id = $1", uuid.UUID(job_id)
        )


async def run_pipeline(
    ctx: dict,
    job_id: str,
    user_id: str,
    restart: bool = False,
) -> str:
    """Execute the full pipeline for a job.

    ``user_id`` is passed in the arq payload so the worker can set its RLS
    context without needing a bypass role.
    """
    pool = await _get_db_pool(ctx)
    logger.info("[worker] starting job=%s user=%s restart=%s", job_id, user_id, restart)

    if restart:
        await _clear_stages(pool, job_id, user_id)
    else:
        await _reset_stale_stages(pool, job_id, user_id)

    last_completed = await _last_completed_stage(pool, job_id, user_id)
    start_index = next_stage_index(last_completed)
    if last_completed:
        logger.info(
            "[worker] job=%s resuming after '%s' (stage %d/%d)",
            job_id,
            last_completed,
            start_index,
            len(PIPELINE_STAGES),
        )

    stage_ctx = {
        "provider_pool": ctx["provider_pool"],
        "db_pool": pool,
        "user_id": user_id,
    }

    for status, stage_name in PIPELINE_STAGES[start_index:]:
        handler = STAGE_HANDLERS[stage_name]
        await _set_status(pool, job_id, user_id, status)
        stage_id = await _create_stage(pool, job_id, user_id, stage_name)

        try:
            output = await handler(job_id, stage_ctx)
        except Exception as exc:
            logger.exception("[worker] job=%s stage '%s' failed", job_id, stage_name)
            await _fail_stage(pool, stage_id, user_id, str(exc))
            await _set_status(pool, job_id, user_id, "failed")
            raise

        await _complete_stage(pool, stage_id, user_id, output or {})
        logger.info("[worker] job=%s stage '%s' completed", job_id, stage_name)

    await _set_status(pool, job_id, user_id, "done")
    logger.info("[worker] job=%s pipeline completed", job_id)
    return "done"


async def startup(ctx: dict) -> None:
    """Worker startup hook — initialize shared resources."""
    logger.info("[worker] starting up")
    await _get_db_pool(ctx)
    ctx["provider_pool"] = get_provider_pool()


async def shutdown(ctx: dict) -> None:
    """Worker shutdown hook — clean up shared resources."""
    logger.info("[worker] shutting down")
    if "db_pool" in ctx:
        await ctx["db_pool"].close()


class WorkerSettings:
    """arq worker configuration."""

    functions = [run_pipeline]
    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)

    max_jobs = 5
    job_timeout = 900  # a 6-stage pipeline with web fetches needs headroom
    max_tries = 2  # one retry; the resume logic makes it cheap
    keep_result = 3600
    health_check_interval = 60
