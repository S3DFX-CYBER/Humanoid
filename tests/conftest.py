import os
import uuid

import asyncpg
import pytest
import pytest_asyncio

from api.config import get_settings


async def db_reachable() -> bool:
    """True when a Postgres instance is reachable (call from async code)."""
    dsn = get_settings().database_url
    if not dsn or os.environ.get("SKIP_DB_TESTS") == "1":
        return False

    try:
        conn = await asyncpg.connect(dsn=dsn, timeout=3)
    except Exception:
        return False
    try:
        return await conn.fetchval("SELECT 1") == 1
    finally:
        await conn.close()


def database_available() -> bool:
    """Synchronous probe for skip markers evaluated at import time."""
    import asyncio

    try:
        return asyncio.run(db_reachable())
    except RuntimeError:  # already inside an event loop
        return True


requires_db = pytest.mark.skipif(
    not database_available(),
    reason="No reachable Postgres — start one with `docker compose up postgres`.",
)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _reset_pool_between_tests():
    """Drop the module-level pool after each test.

    asyncpg pools are bound to the event loop that created them, and pytest
    gives every test a fresh loop, so a reused pool fails with
    "connection was closed in the middle of operation".
    """
    yield
    from api.database import close_pool

    await close_pool()


@pytest_asyncio.fixture
async def db_pool():
    """Shared pool for integration tests; torn down at the end."""
    from api.database import close_pool, get_pool

    pool = await get_pool()
    yield pool
    await close_pool()


@pytest.fixture
def user_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def other_user_id() -> str:
    return str(uuid.uuid4())
