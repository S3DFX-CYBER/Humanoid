"""Tests for in-place upgrades of the local auth.uid() stub."""

import uuid
from pathlib import Path

import pytest

from api.database import get_pool


@pytest.mark.asyncio
async def test_auth_uid_upgrade_reads_request_jwt_claim_sub():
    """Upgrade an old jwt.claims.sub stub and verify the request claim wins."""
    migration_sql = Path(
        "db/migrations/202607260001_update_auth_uid_request_claim.sql"
    ).read_text()
    subject = uuid.uuid4()
    stale_subject = uuid.uuid4()

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS auth")
        await conn.execute("""
            CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $func$
            SELECT NULLIF(current_setting('jwt.claims.sub', true), '')::uuid;
            $func$ LANGUAGE SQL STABLE;
            """)

        await conn.execute(migration_sql)
        await conn.execute(
            "SELECT set_config($1, $2, false)",
            "jwt.claims.sub",
            str(stale_subject),
        )
        await conn.execute(
            "SELECT set_config($1, $2, false)",
            "request.jwt.claim.sub",
            str(subject),
        )

        assert await conn.fetchval("SELECT auth.uid()") == subject
