"""Tests for the in-place upgrade of the local auth.uid() stub."""

import uuid
from pathlib import Path

from tests.conftest import requires_db

pytestmark = requires_db

MIGRATION = Path("db/migrations/202607260001_update_auth_uid_request_claim.sql")


async def test_migration_upgrades_a_stale_stub(db_pool):
    migration_sql = MIGRATION.read_text()
    subject = uuid.uuid4()
    stale_subject = uuid.uuid4()

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("CREATE SCHEMA IF NOT EXISTS auth")
            await conn.execute(
                """
                CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS $func$
                SELECT NULLIF(current_setting('jwt.claims.sub', true), '')::uuid;
                $func$ LANGUAGE SQL STABLE;
                """
            )

            await conn.execute(migration_sql)
            await conn.execute(
                "SELECT set_config('jwt.claims.sub', $1, true)", str(stale_subject)
            )
            await conn.execute(
                "SELECT set_config('request.jwt.claim.sub', $1, true)", str(subject)
            )

            assert await conn.fetchval("SELECT auth.uid()") == subject


async def test_migration_is_idempotent(db_pool):
    migration_sql = MIGRATION.read_text()

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(migration_sql)
            await conn.execute(migration_sql)
            exists = await conn.fetchval(
                "SELECT to_regprocedure('auth.uid()')"
            )
            assert exists is not None
