"""Async database connection pool using asyncpg.

Every query that touches user data runs inside a transaction that first sets
Supabase's ``request.jwt.claim.sub`` session setting, which the ``auth.uid()``
stub in ``db/schema.sql`` reads.  Row-Level Security then scopes every row to
the caller, so the application role itself needs no row filtering.
"""

import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from api.config import get_settings

RLS_USER_CLAIM = "request.jwt.claim.sub"


async def init_connection(conn: asyncpg.Connection) -> None:
    """Register JSON codecs so jsonb columns accept and return dicts."""
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def set_rls_context(conn: asyncpg.Connection, user_id: str) -> None:
    """Set Supabase-compatible auth.uid() context for this transaction."""
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
            init=init_connection,
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def user_connection(
    pool: asyncpg.Pool, user_id: str
) -> AsyncIterator[asyncpg.Connection]:
    """Acquire a connection with the RLS context set for ``user_id``."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await set_rls_context(conn, user_id)
            yield conn


async def fetch_one(
    query: str, *args, user_id: str | None = None
) -> asyncpg.Record | None:
    """Execute a query and return a single row, optionally setting RLS context."""
    pool = await get_pool()
    if user_id:
        async with user_connection(pool, user_id) as conn:
            return await conn.fetchrow(query, *args)
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetch_all(
    query: str, *args, user_id: str | None = None
) -> list[asyncpg.Record]:
    """Execute a query and return all rows, optionally setting RLS context."""
    pool = await get_pool()
    if user_id:
        async with user_connection(pool, user_id) as conn:
            return await conn.fetch(query, *args)
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def execute(query: str, *args, user_id: str | None = None) -> str:
    """Execute a query and return the status string, optionally setting RLS context."""
    pool = await get_pool()
    if user_id:
        async with user_connection(pool, user_id) as conn:
            return await conn.execute(query, *args)
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


async def ensure_user(user_id: str, email: str | None = None) -> None:
    """Make sure a local ``users`` row exists for an authenticated subject.

    Supabase keeps identities in ``auth.users``; the application tables key off
    ``public.users``, so the row is created on first sight instead of failing
    the ``jobs.user_id`` foreign key.
    """
    await execute(
        """
        INSERT INTO users (id, email) VALUES ($1, $2)
        ON CONFLICT (id) DO NOTHING
        """,
        user_id,
        email or f"{user_id}@users.humanoid.local",
        user_id=user_id,
    )
