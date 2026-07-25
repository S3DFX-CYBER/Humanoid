"""Tests verifying that database Row-Level Security correctly isolates data."""

import pytest
import uuid
import asyncpg
from api.database import fetch_one, fetch_all, execute

@pytest.fixture
def test_user_a():
    return str(uuid.uuid4())

@pytest.fixture
def test_user_b():
    return str(uuid.uuid4())

@pytest.fixture
def test_job_id():
    return str(uuid.uuid4())

@pytest.mark.asyncio
async def test_rls_job_isolation(test_user_a, test_user_b, test_job_id):
    """Verify that user_b cannot read a job created by user_a."""
    
    # Create users first to satisfy foreign key constraints
    await execute("INSERT INTO users (id, email) VALUES ($1, $2)", uuid.UUID(test_user_a), f"{test_user_a}@test.local", user_id=test_user_a)
    await execute("INSERT INTO users (id, email) VALUES ($1, $2)", uuid.UUID(test_user_b), f"{test_user_b}@test.local", user_id=test_user_b)
    
    # User A creates a job
    await execute(
        "INSERT INTO jobs (id, user_id, topic, status) VALUES ($1, $2, $3, 'queued')",
        uuid.UUID(test_job_id),
        uuid.UUID(test_user_a),
        "Test Topic",
        user_id=test_user_a
    )
    
    # User A can fetch the job successfully
    row = await fetch_one("SELECT * FROM jobs WHERE id = $1", uuid.UUID(test_job_id), user_id=test_user_a)
    assert row is not None
    assert row["topic"] == "Test Topic"
    
    # User B attempting to fetch the job resolves to None due to RLS
    row = await fetch_one("SELECT * FROM jobs WHERE id = $1", uuid.UUID(test_job_id), user_id=test_user_b)
    assert row is None
