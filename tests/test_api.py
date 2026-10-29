"""API contract tests.

Requests that never reach the database are exercised without Postgres; the
rest are gated behind ``requires_db``.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_current_user
from api.main import app
from api.routes.jobs import get_arq_pool
from tests.conftest import db_reachable, requires_db


class FakeArq:
    """Records enqueued jobs instead of talking to Redis."""

    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.enqueued.append((name, args, kwargs))
        return None


@pytest.fixture
def fake_arq():
    return FakeArq()


@pytest_asyncio.fixture
async def client_factory(fake_arq, user_id):
    if await db_reachable():
        from api.database import ensure_user

        await ensure_user(user_id)

    def _build():
        app.dependency_overrides[get_current_user] = lambda: user_id
        app.dependency_overrides[get_arq_pool] = lambda: fake_arq
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    yield _build
    app.dependency_overrides.clear()


async def test_topic_validation_rejects_short_topics(client_factory):
    async with client_factory() as client:
        response = await client.post("/jobs", json={"topic": "ab"})
    assert response.status_code == 422


async def test_unknown_citation_style_is_rejected(client_factory):
    async with client_factory() as client:
        response = await client.post(
            "/jobs", json={"topic": "A valid topic", "citation_style": "harvard"}
        )
    assert response.status_code == 422


async def test_health_endpoint(client_factory):
    async with client_factory() as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "humanoid-api"


async def test_malformed_job_id_returns_404_not_500(client_factory):
    async with client_factory() as client:
        response = await client.get("/jobs/not-a-uuid")
    assert response.status_code == 404


@requires_db
async def test_create_and_fetch_job(client_factory, fake_arq, user_id):
    async with client_factory() as client:
        created = await client.post(
            "/jobs",
            json={
                "topic": "Retrieval augmented generation",
                "citation_style": "apa",
            },
        )
        assert created.status_code == 201, created.text
        body = created.json()

        fetched = await client.get(f"/jobs/{body['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["topic"] == "Retrieval augmented generation"

    assert fake_arq.enqueued
    name, args, _ = fake_arq.enqueued[-1]
    assert name == "run_pipeline"
    assert args[0] == body["id"]
    assert args[1] == user_id


@requires_db
async def test_document_is_404_before_the_pipeline_finishes(client_factory):
    async with client_factory() as client:
        created = await client.post("/jobs", json={"topic": "An unfinished job"})
        job_id = created.json()["id"]

        document = await client.get(f"/jobs/{job_id}/document")
        assert document.status_code == 200
        assert document.json()["has_docx"] is False

        download = await client.get(f"/jobs/{job_id}/document/file")
        assert download.status_code == 404


@requires_db
async def test_retry_rejects_a_queued_job(client_factory):
    async with client_factory() as client:
        created = await client.post("/jobs", json={"topic": "Retry behaviour"})
        job_id = created.json()["id"]
        response = await client.post(f"/jobs/{job_id}/retry")
    assert response.status_code == 409


@requires_db
async def test_jobs_are_not_visible_across_users(client_factory, fake_arq):
    async with client_factory() as client:
        created = await client.post("/jobs", json={"topic": "Private job"})
        job_id = created.json()["id"]

    other_user = str(uuid.uuid4())
    app.dependency_overrides[get_current_user] = lambda: other_user
    app.dependency_overrides[get_arq_pool] = lambda: fake_arq

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/jobs/{job_id}")
    assert response.status_code == 404
