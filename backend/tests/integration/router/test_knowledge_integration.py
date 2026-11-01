from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.api.routers import knowledge
from src.db.db_connection import get_db
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.db.models.background_jobs import BackgroundJob, JobStatus, JobType
from src.dependencies import (
    get_arq_pool,
    get_background_job_repo,
    get_config_bundle_service,
    get_knowledge_service,
    get_pack_repo,
)
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.background_job_repo import BackgroundJobRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.config_bundle_service import ConfigBundleService
from src.services.knowledge_service import KnowledgeService
from src.worker.queues import INGESTION_QUEUE

pytestmark = [pytest.mark.integration, pytest.mark.db]


@pytest.fixture
def arq_pool():
    pool = AsyncMock()
    pool.enqueue_job.return_value = object()
    return pool


@pytest.fixture
def knowledge_service():
    return AsyncMock(spec=KnowledgeService)


@pytest.fixture
def app(db_session, build_app, arq_pool, knowledge_service):
    bundle_service = ConfigBundleService(
        ConfigBundleRepository(db_session),
        SkillRepository(db_session),
        ToolDefinitionRepository(db_session),
        KnowledgePackRepository(db_session),
        AgentProfileRepository(db_session),
    )
    application = build_app(knowledge.router)
    application.dependency_overrides[get_db] = lambda: db_session
    application.dependency_overrides[get_background_job_repo] = lambda: BackgroundJobRepository(db_session)
    application.dependency_overrides[get_pack_repo] = lambda: KnowledgePackRepository(db_session)
    application.dependency_overrides[get_arq_pool] = lambda: arq_pool
    application.dependency_overrides[get_knowledge_service] = lambda: knowledge_service
    application.dependency_overrides[get_config_bundle_service] = lambda: bundle_service
    return application


@pytest.fixture(autouse=True)
def real_actor(default_actor, sample_user):
    default_actor.id = sample_user.id
    return default_actor


def web_payload(pack_id, **overrides):
    payload = {
        "query": "python async",
        "document_type": DocumentType.BOOK.value,
        "knowledge_type": KnowledgeType.REFERENCE.value,
        "knowledge_pack_id": pack_id,
    }
    payload.update(overrides)
    return payload


def file_payload(pack_id, **overrides):
    payload = {
        "source": "docs/book.pdf",
        "document_type": DocumentType.BOOK.value,
        "knowledge_type": KnowledgeType.REFERENCE.value,
        "knowledge_pack_id": pack_id,
    }
    payload.update(overrides)
    return payload


async def latest_job(db_session):
    result = await db_session.execute(
        select(BackgroundJob)
        .order_by(BackgroundJob.id.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


ADMIN_ONLY_ENDPOINTS = [
    ("POST", "/knowledge/ingest/file"),
    ("POST", "/knowledge/ingest/web"),
    ("GET", "/knowledge/ingest/jobs/1"),
]


@pytest.mark.parametrize("method, url", ADMIN_ONLY_ENDPOINTS)
async def test_admin_endpoints_reject_regular_user(client, method, url):
    response = await client.request(method, url, json={})

    assert response.status_code == 403, response.text


async def test_ingest_file_returns_400_when_service_rejects(
    client, as_admin, knowledge_service, sample_knowledge_pack
):
    knowledge_service.ingest_file.side_effect = ValueError("bad source")

    response = await client.post("/knowledge/ingest/file", json=file_payload(sample_knowledge_pack.id))

    assert response.status_code == 400, response.text
    assert "bad source" in response.json()["detail"]


async def test_ingest_web_creates_job_and_enqueues_it(
    client, as_admin, arq_pool, db_session, sample_knowledge_pack
):
    response = await client.post("/knowledge/ingest/web", json=web_payload(sample_knowledge_pack.id))

    assert response.status_code == 202, response.text
    body = response.json()
    job = await latest_job(db_session)
    assert body["job_id"] == job.id
    assert body["status"] == JobStatus.PENDING.value
    assert job.job_type == JobType.DISCOVERY_INGEST.value
    assert job.user_id == as_admin.id
    arq_pool.enqueue_job.assert_awaited_once()
    args = arq_pool.enqueue_job.await_args
    assert args.args[0] == "run_discovery_ingest"
    assert args.args[1] == job.id
    assert args.kwargs["_job_id"] == f"discovery_ingest:{job.id}"
    assert args.kwargs["_queue_name"] == INGESTION_QUEUE
    assert args.kwargs["knowledge_pack_id"] == sample_knowledge_pack.id


async def test_ingest_web_unknown_pack_returns_400_and_creates_no_job(
    client, as_admin, arq_pool, db_session
):
    before = await db_session.execute(select(BackgroundJob.id))
    count_before = len(before.scalars().all())

    response = await client.post("/knowledge/ingest/web", json=web_payload(999999))

    assert response.status_code == 400, response.text
    assert "999999" in response.json()["detail"]
    after = await db_session.execute(select(BackgroundJob.id))
    assert len(after.scalars().all()) == count_before
    arq_pool.enqueue_job.assert_not_awaited()


async def test_ingest_web_archived_pack_returns_400(
    client, as_admin, db_session, sample_knowledge_pack
):
    pack_repo = KnowledgePackRepository(db_session)
    await pack_repo.archive(sample_knowledge_pack)

    response = await client.post("/knowledge/ingest/web", json=web_payload(sample_knowledge_pack.id))

    assert response.status_code == 400, response.text


async def test_ingest_web_invalid_body_returns_422(client, as_admin):
    response = await client.post("/knowledge/ingest/web", json={"query": "only query"})

    assert response.status_code == 422, response.text


async def test_ingest_web_enqueue_failure_returns_503_and_fails_job(
    client, as_admin, arq_pool, db_session, sample_knowledge_pack
):
    arq_pool.enqueue_job.side_effect = Exception("redis down")

    response = await client.post("/knowledge/ingest/web", json=web_payload(sample_knowledge_pack.id))

    assert response.status_code == 503, response.text
    job = await latest_job(db_session)
    assert job.status == JobStatus.FAILED.value
    assert "Enqueue failed" in job.error


async def test_ingest_web_duplicate_arq_job_returns_409_and_fails_job(
    client, as_admin, arq_pool, db_session, sample_knowledge_pack
):
    arq_pool.enqueue_job.return_value = None

    response = await client.post("/knowledge/ingest/web", json=web_payload(sample_knowledge_pack.id))

    assert response.status_code == 409, response.text
    job = await latest_job(db_session)
    assert job.status == JobStatus.FAILED.value
    assert job.error == "Duplicate arq job id"


async def test_created_job_can_be_fetched(client, as_admin, sample_knowledge_pack):
    created = await client.post("/knowledge/ingest/web", json=web_payload(sample_knowledge_pack.id))
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]

    response = await client.get(f"/knowledge/ingest/jobs/{job_id}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == JobStatus.PENDING.value


async def test_get_unknown_job_returns_404(client, as_admin):
    response = await client.get("/knowledge/ingest/jobs/999999")

    assert response.status_code == 404, response.text


async def test_get_job_of_another_type_returns_404(client, as_admin, db_session):
    job = await BackgroundJobRepository(db_session).create(
        job_type=JobType.SKILL_GENERATION, user_id=as_admin.id, payload={}
    )

    response = await client.get(f"/knowledge/ingest/jobs/{job.id}")

    assert response.status_code == 404, response.text


async def test_search_without_bundle_id_returns_422(client, knowledge_service):
    response = await client.post("/knowledge/search", json={"query": "q"})

    assert response.status_code == 422, response.text
    knowledge_service.search.assert_not_awaited()


async def test_search_in_foreign_bundle_returns_404(
    client, knowledge_service, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.post(
        "/knowledge/search", json={"query": "q", "config_bundle_id": bundle.id}
    )

    assert response.status_code == 404, response.text
    knowledge_service.search.assert_not_awaited()


async def test_search_in_own_bundle_calls_service(
    client, knowledge_service, sample_user, make_agent, make_bundle
):
    bundle = await make_bundle(sample_user, await make_agent())
    knowledge_service.search.return_value = []

    response = await client.post(
        "/knowledge/search", json={"query": "q", "config_bundle_id": bundle.id}
    )

    assert response.status_code == 200, response.text
    assert response.json() == []
    knowledge_service.search.assert_awaited_once()
    assert knowledge_service.search.await_args.kwargs["config_bundle_id"] == bundle.id
    assert knowledge_service.search.await_args.kwargs["query"] == "q"


async def test_search_as_admin_can_use_foreign_bundle(
    client, as_admin, knowledge_service, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())
    knowledge_service.search.return_value = []

    response = await client.post(
        "/knowledge/search", json={"query": "q", "config_bundle_id": bundle.id}
    )

    assert response.status_code == 200, response.text


async def test_search_service_value_error_returns_400(
    client, knowledge_service, sample_user, make_agent, make_bundle
):
    bundle = await make_bundle(sample_user, await make_agent())
    knowledge_service.search.side_effect = ValueError("broken")

    response = await client.post(
        "/knowledge/search", json={"query": "q", "config_bundle_id": bundle.id}
    )

    assert response.status_code == 400, response.text
    assert "broken" in response.json()["detail"]


async def test_search_agentic_without_bundle_id_returns_422(client):
    response = await client.post("/knowledge/search/agentic", json={"query": "q"})

    assert response.status_code == 422, response.text


async def test_search_agentic_in_foreign_bundle_returns_404(
    client, another_user, make_agent, make_bundle
):
    bundle = await make_bundle(another_user, await make_agent())

    response = await client.post(
        "/knowledge/search/agentic", json={"query": "q", "config_bundle_id": bundle.id}
    )

    assert response.status_code == 404, response.text


async def test_search_agentic_without_context_returns_empty_response(
    client, knowledge_service, sample_user, make_agent, make_bundle
):
    bundle = await make_bundle(sample_user, await make_agent())
    knowledge_service.search_agentic.return_value = None

    response = await client.post(
        "/knowledge/search/agentic", json={"query": "q", "config_bundle_id": bundle.id}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["initial_subqueries"] == []
    assert body["evidence"] == []
    assert body["iterations"] == []
    assert body["degraded_to_hybrid"] is False