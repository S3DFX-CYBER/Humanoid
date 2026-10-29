"""Row-Level Security isolation tests.

The application role (``humanoid_app``) is a non-owner, so RLS applies to it.
These tests switch into that role to prove the policies actually bite.
"""

import uuid

import pytest

from tests.conftest import requires_db

pytestmark = requires_db

APP_ROLE = "humanoid_app"


async def _seed_users(conn, *user_ids):
    for user_id in user_ids:
        await conn.execute(
            """
            INSERT INTO users (id, email) VALUES ($1, $2)
            ON CONFLICT (id) DO NOTHING
            """,
            uuid.UUID(user_id),
            f"{user_id}@test.local",
        )


async def test_job_is_visible_only_to_its_owner(db_pool, user_id, other_user_id):
    job_id = uuid.uuid4()

    async with db_pool.acquire() as conn:
        await _seed_users(conn, user_id, other_user_id)
        async with conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {APP_ROLE}")
            await conn.execute(
                "SELECT set_config('request.jwt.claim.sub', $1, true)", user_id
            )
            await conn.execute(
                """
                INSERT INTO jobs (id, user_id, topic, status)
                VALUES ($1, $2, 'RLS test topic', 'queued')
                """,
                job_id,
                uuid.UUID(user_id),
            )

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {APP_ROLE}")
            await conn.execute(
                "SELECT set_config('request.jwt.claim.sub', $1, true)", user_id
            )
            assert await conn.fetchval(
                "SELECT count(*) FROM jobs WHERE id = $1", job_id
            ) == 1

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {APP_ROLE}")
            await conn.execute(
                "SELECT set_config('request.jwt.claim.sub', $1, true)", other_user_id
            )
            assert await conn.fetchval(
                "SELECT count(*) FROM jobs WHERE id = $1", job_id
            ) == 0


async def test_no_context_means_no_rows(db_pool, user_id):
    job_id = uuid.uuid4()

    async with db_pool.acquire() as conn:
        await _seed_users(conn, user_id)
        async with conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {APP_ROLE}")
            await conn.execute(
                "SELECT set_config('request.jwt.claim.sub', $1, true)", user_id
            )
            await conn.execute(
                """
                INSERT INTO jobs (id, user_id, topic, status)
                VALUES ($1, $2, 'No context topic', 'queued')
                """,
                job_id,
                uuid.UUID(user_id),
            )

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {APP_ROLE}")
            await conn.execute("SELECT set_config('request.jwt.claim.sub', '', true)")
            assert await conn.fetchval("SELECT count(*) FROM jobs") == 0


async def test_cannot_insert_a_job_for_another_user(db_pool, user_id, other_user_id):
    async with db_pool.acquire() as conn:
        await _seed_users(conn, user_id, other_user_id)

        with pytest.raises(Exception):
            async with conn.transaction():
                await conn.execute(f"SET LOCAL ROLE {APP_ROLE}")
                await conn.execute(
                    "SELECT set_config('request.jwt.claim.sub', $1, true)", user_id
                )
                await conn.execute(
                    """
                    INSERT INTO jobs (id, user_id, topic, status)
                    VALUES ($1, $2, 'Spoofed job', 'queued')
                    """,
                    uuid.uuid4(),
                    uuid.UUID(other_user_id),
                )


async def test_documents_are_scoped_to_the_job_owner(db_pool, user_id, other_user_id):
    job_id = uuid.uuid4()

    async with db_pool.acquire() as conn:
        await _seed_users(conn, user_id, other_user_id)
        async with conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {APP_ROLE}")
            await conn.execute(
                "SELECT set_config('request.jwt.claim.sub', $1, true)", user_id
            )
            await conn.execute(
                """
                INSERT INTO jobs (id, user_id, topic, status)
                VALUES ($1, $2, 'Document scope', 'queued')
                """,
                job_id,
                uuid.UUID(user_id),
            )
            await conn.execute(
                """
                INSERT INTO documents (job_id, kind, filename, mime_type,
                                       content, byte_size)
                VALUES ($1, 'docx', 'x.docx', 'application/octet-stream',
                        $2, $3)
                ON CONFLICT (job_id, kind) DO NOTHING
                """,
                job_id,
                b"bytes",
                5,
            )

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL ROLE {APP_ROLE}")
            await conn.execute(
                "SELECT set_config('request.jwt.claim.sub', $1, true)", other_user_id
            )
            assert await conn.fetchval("SELECT count(*) FROM documents") == 0
