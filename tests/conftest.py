import pytest
import asyncpg
import asyncio
import os
from contextlib import asynccontextmanager

from api.database import close_pool, get_pool
from api.config import get_settings

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest.fixture(scope="session", autouse=True)
async def db_pool():
    """Setup a clean test database pool."""
    # Ensure tests are running against the local test database via ENVIRONMENT or explicit URL override.
    settings = get_settings()
    pool = await get_pool()
    
    # We could theoretically truncate tables here if needed,
    # but since jobs are isolated by UUID, it is safe without truncating 
    # as long as we generate fresh UUIDs for test users.
    
    yield pool
    
    await close_pool()
