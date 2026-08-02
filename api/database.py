"""Async database connection pool using asyncpg."""

import asyncpg
from api.config import get_settings

RLS_USER_CLAIM = "request.jwt.claim.sub"


async def set_rls_context(conn: asyncpg.Connection, user_id: str) -> None:
    """Set Supabase-compatible auth.uid() context for this transaction.

    Supabase's built-in auth.uid() reads request.jwt.claim.sub. Local Postgres
    uses the same setting via the schema.sql stub so CI and production match.
    """
    await conn.execute("SELECT set_config($1, $2, true)", RLS_USER_CLAIM, str(user_id))


_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def fetch_one(
    query: str, *args, user_id: str | None = None
) -> asyncpg.Record | None:
    """Execute a query and return a single row, optionally setting RLS context."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user_id:
            async with conn.transaction():
                await set_rls_context(conn, user_id)
                return await conn.fetchrow(query, *args)
        return await conn.fetchrow(query, *args)


async def fetch_all(
    query: str, *args, user_id: str | None = None
) -> list[asyncpg.Record]:
    """Execute a query and return all rows, optionally setting RLS context."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user_id:
            async with conn.transaction():
                await set_rls_context(conn, user_id)
                return await conn.fetch(query, *args)
        return await conn.fetch(query, *args)


async def execute(query: str, *args, user_id: str | None = None) -> str:
    """Execute a query and return the status string, optionally setting RLS context."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if user_id:
            async with conn.transaction():
                await set_rls_context(conn, user_id)
                return await conn.execute(query, *args)
        return await conn.execute(query, *args)
