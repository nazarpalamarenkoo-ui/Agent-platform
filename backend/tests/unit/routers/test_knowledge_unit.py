from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec
from datetime import datetime, timezone
from src.db.models.background_jobs import JobStatus, JobType
import pytest

from src.api.routers import knowledge
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.db.models.background_jobs import JobType
from src.dependencies import (
    get_arq_pool,
    get_background_job_repo,
    get_config_bundle_service,
    get_knowledge_service,
    get_pack_repo,
)
from src.knowledge.documents_schema.corpus_build_result import CorpusBuilderResult
from src.repositories.background_job_repo import BackgroundJobRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.services.config_bundle_service import ConfigBundleService
from src.services.errors import NotFoundError
from src.services.knowledge_service import KnowledgeService
from src.worker.queues import INGESTION_QUEUE

pytestmark = pytest.mark.unit

ROUTER = knowledge.router
SERVICE_DEPENDENCY = get_knowledge_service
SERVICE_SPEC = KnowledgeService

BUILD_RESULT_DATA = {
    "succeeded": [1, 2],
    "skipped_duplicates": ["dup.pdf"],
    "failed": [{"source": "bad.pdf", "error": "boom"}],
}
FILE_PAYLOAD = {
    "source": "/data/book.pdf",
    "document_type": DocumentType.BOOK.value,
    "knowledge_type": KnowledgeType.REFERENCE.value,
    "knowledge_pack_id": 1,
}
WEB_PAYLOAD = {
    "query": "fastapi dependency injection",
    "document_type": DocumentType.BOOK.value,
    "knowledge_type": KnowledgeType.REFERENCE.value,
    "knowledge_pack_id": 1,
}
SEARCH_PAYLOAD = {
    "query": "how to design an api",
    "limit": 10,
    "top_n": 5,
    "k": 60,
    "config_bundle_id": 1,
}
AGENTIC_PAYLOAD = {"query": "how to design an api", "config_bundle_id": 1}


def make_search_result(point_id="point-1", score=0.9, **payload):
    return SimpleNamespace(id=point_id, score=score, payload=payload or {"text": "chunk"})


def make_agentic_context(with_iterations=True):
    evidence = [
        SimpleNamespace(
            query="sub-1", chunk_id="chunk-1", score=0.77,
            text="evidence text", metadata={"source": "book.pdf"},
        )
    ]
    iterations = []
    if with_iterations:
        iterations.append(
            SimpleNamespace(
                iteration=1,
                subqueries=["sub-1", "sub-2"],
                new_evidence_count=1,
                total_evidence_count=1,
                evaluation=SimpleNamespace(
                    sufficient=False, coverage=0.5, confidence=0.6, redundancy=0.1,
                    missing_topics=["auth"], retry_queries=["auth in api"],
                ),
            )
        )
    return SimpleNamespace(
        plan=SimpleNamespace(subqueries=["sub-1", "sub-2"], reasoning="split into parts"),
        evidence=evidence,
        iterations=iterations,
    )


@pytest.fixture
def bundle_service(override):
    return override(get_config_bundle_service, create_autospec(ConfigBundleService, instance=True))


@pytest.fixture
def pack_repo(override):
    repo = create_autospec(KnowledgePackRepository, instance=True)
    repo.get_active.return_value = SimpleNamespace(id=1)
    return override(get_pack_repo, repo)


@pytest.fixture
def job_repo(override):
    repo = create_autospec(BackgroundJobRepository, instance=True)
    repo.create.return_value = SimpleNamespace(id=42, status="pending")
    return override(get_background_job_repo, repo)


@pytest.fixture
def arq_pool(override):
    pool = AsyncMock()
    pool.enqueue_job.return_value = object()
    return override(get_arq_pool, pool)


class TestIngestFile:
    async def test_admin_gets_201_with_build_result(self, client, service, as_admin):
        result = CorpusBuilderResult(**BUILD_RESULT_DATA)
        service.ingest_file.return_value = result

        response = await client.post("/knowledge/ingest/file", json=FILE_PAYLOAD)

        assert response.status_code == 201
        assert response.json() == result.model_dump(mode="json")
        service.ingest_file.assert_awaited_once_with(
            source="/data/book.pdf",
            document_type=DocumentType.BOOK,
            knowledge_type=KnowledgeType.REFERENCE,
            knowledge_pack_id=1,
        )

    async def test_regular_user_is_forbidden(self, client, service):
        response = await client.post("/knowledge/ingest/file", json=FILE_PAYLOAD)

        assert response.status_code == 403
        service.ingest_file.assert_not_awaited()

    async def test_value_error_returns_400(self, client, service, as_admin):
        service.ingest_file.side_effect = ValueError("Unsupported mime type")

        response = await client.post("/knowledge/ingest/file", json=FILE_PAYLOAD)

        assert response.status_code == 400
        assert response.json()["detail"] == "Unsupported mime type"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {**FILE_PAYLOAD, "document_type": "nope"},
            {**FILE_PAYLOAD, "knowledge_type": "nope"},
            {**FILE_PAYLOAD, "knowledge_pack_id": "abc"},
            {k: v for k, v in FILE_PAYLOAD.items() if k != "source"},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, as_admin, payload):
        response = await client.post("/knowledge/ingest/file", json=payload)

        assert response.status_code == 422
        service.ingest_file.assert_not_awaited()


class TestIngestWeb:
    async def test_creates_job_and_enqueues_it(
        self, client, service, as_admin, pack_repo, job_repo, arq_pool
    ):
        response = await client.post("/knowledge/ingest/web", json=WEB_PAYLOAD)

        assert response.status_code == 202
        assert response.json() == {"job_id": 42, "status": "pending"}
        pack_repo.get_active.assert_awaited_once_with(1)

        kwargs = job_repo.create.await_args.kwargs
        assert kwargs["job_type"] == JobType.DISCOVERY_INGEST
        assert kwargs["user_id"] == as_admin.id
        assert kwargs["payload"].items() >= WEB_PAYLOAD.items()

        arq_pool.enqueue_job.assert_awaited_once_with(
            "run_discovery_ingest",
            42,
            **kwargs["payload"],
            _job_id="discovery_ingest:42",
            _queue_name=INGESTION_QUEUE,
        )
        service.ingest_from_web.assert_not_called()

    async def test_regular_user_is_forbidden(self, client, service, pack_repo, job_repo, arq_pool):
        response = await client.post("/knowledge/ingest/web", json=WEB_PAYLOAD)

        assert response.status_code == 403
        job_repo.create.assert_not_awaited()
        arq_pool.enqueue_job.assert_not_awaited()

    async def test_missing_pack_returns_400_before_creating_job(
        self, client, service, as_admin, pack_repo, job_repo, arq_pool
    ):
        pack_repo.get_active.return_value = None

        response = await client.post("/knowledge/ingest/web", json=WEB_PAYLOAD)

        assert response.status_code == 400
        assert "does not exist or is archived" in response.json()["detail"]
        job_repo.create.assert_not_awaited()
        arq_pool.enqueue_job.assert_not_awaited()

    async def test_enqueue_failure_marks_job_failed_and_returns_503(
        self, client, service, as_admin, pack_repo, job_repo, arq_pool
    ):
        arq_pool.enqueue_job.side_effect = ConnectionError("redis down")

        response = await client.post("/knowledge/ingest/web", json=WEB_PAYLOAD)

        assert response.status_code == 503
        assert response.json()["detail"] == "Queue unavailable"
        job_repo.mark_failed.assert_awaited_once_with(42, "Enqueue failed: redis down")

    async def test_duplicate_arq_job_returns_409(
        self, client, service, as_admin, pack_repo, job_repo, arq_pool
    ):
        arq_pool.enqueue_job.return_value = None

        response = await client.post("/knowledge/ingest/web", json=WEB_PAYLOAD)

        assert response.status_code == 409
        job_repo.mark_failed.assert_awaited_once_with(42, "Duplicate arq job id")

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {**WEB_PAYLOAD, "document_type": "nope"},
            {**WEB_PAYLOAD, "knowledge_type": "nope"},
            {**WEB_PAYLOAD, "query": ["x"]},
            {**WEB_PAYLOAD, "knowledge_pack_id": "abc"},
        ],
    )
    async def test_rejects_invalid_payload(
        self, client, service, as_admin, pack_repo, job_repo, arq_pool, payload
    ):
        response = await client.post("/knowledge/ingest/web", json=payload)

        assert response.status_code == 422
        job_repo.create.assert_not_awaited()


class TestGetIngestJob:
    async def test_regular_user_is_forbidden(self, client, service, job_repo):
        response = await client.get("/knowledge/ingest/jobs/42")

        assert response.status_code == 403
        job_repo.get.assert_not_awaited()

    async def test_unknown_job_returns_404(self, client, service, as_admin, job_repo):
        job_repo.get.return_value = None

        response = await client.get("/knowledge/ingest/jobs/42")

        assert response.status_code == 404
        job_repo.get.assert_awaited_once_with(42)
        
    async def test_returns_job_status(self, client, service, as_admin, job_repo):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        job_repo.get.return_value = SimpleNamespace(
            id=42,
            job_type=JobType.DISCOVERY_INGEST.value,
            status=JobStatus.DONE.value,
            result={"succeeded": [1]},
            error=None,
            created_at=now,
            started_at=now,
            finished_at=now,
        )

        response = await client.get("/knowledge/ingest/jobs/42")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 42
        assert body["status"] == "done"
        assert body["result"] == {"succeeded": [1]}
        assert body["error"] is None
        
    async def test_job_of_other_type_returns_404(self, client, service, as_admin, job_repo):
        other_type = next(t for t in JobType if t != JobType.DISCOVERY_INGEST)
        job_repo.get.return_value = SimpleNamespace(id=42, job_type=other_type.value)

        response = await client.get("/knowledge/ingest/jobs/42")

        assert response.status_code == 404

    async def test_invalid_id(self, client, service, as_admin, job_repo):
        response = await client.get("/knowledge/ingest/jobs/abc")

        assert response.status_code == 422


class TestSearch:
    async def test_member_of_bundle_gets_results(self, client, service, bundle_service, actor):
        service.search.return_value = [
            make_search_result("point-1", 0.9, text="first"),
            make_search_result("point-2", 0.5, text="second"),
        ]

        response = await client.post("/knowledge/search", json=SEARCH_PAYLOAD)

        assert response.status_code == 200
        assert response.json() == [
            {"id": "point-1", "score": 0.9, "payload": {"text": "first"}},
            {"id": "point-2", "score": 0.5, "payload": {"text": "second"}},
        ]
        bundle_service.get_bundle.assert_awaited_once_with(1, actor.id)
        service.search.assert_awaited_once_with(
            query="how to design an api", limit=10, top_n=5, k=60, config_bundle_id=1
        )

    async def test_admin_skips_bundle_ownership_check(self, client, service, bundle_service, as_admin):
        service.search.return_value = []

        response = await client.post("/knowledge/search", json=SEARCH_PAYLOAD)

        assert response.status_code == 200
        assert response.json() == []
        bundle_service.get_bundle.assert_not_awaited()

    async def test_foreign_bundle_returns_404_and_skips_search(self, client, service, bundle_service):
        bundle_service.get_bundle.side_effect = NotFoundError("nf")

        response = await client.post("/knowledge/search", json=SEARCH_PAYLOAD)

        assert response.status_code == 404
        assert response.json()["detail"] == "Config bundle not found"
        service.search.assert_not_awaited()

    async def test_missing_bundle_id_is_rejected_by_schema(self, client, service, bundle_service):
        response = await client.post("/knowledge/search", json={**SEARCH_PAYLOAD, "config_bundle_id": None})

        assert response.status_code == 422
        service.search.assert_not_awaited()
        bundle_service.get_bundle.assert_not_awaited()

    async def test_value_error_returns_400(self, client, service, bundle_service):
        service.search.side_effect = ValueError("ConfigBundle with id=1 does not exist")

        response = await client.post("/knowledge/search", json=SEARCH_PAYLOAD)

        assert response.status_code == 400
        assert response.json()["detail"] == "ConfigBundle with id=1 does not exist"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {**SEARCH_PAYLOAD, "query": ["x"]},
            {**SEARCH_PAYLOAD, "limit": "abc"},
            {**SEARCH_PAYLOAD, "config_bundle_id": "abc"},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, bundle_service, payload):
        response = await client.post("/knowledge/search", json=payload)

        assert response.status_code == 422
        service.search.assert_not_awaited()


class TestSearchAgentic:
    async def test_maps_full_context(self, client, service, bundle_service, actor):
        service.search_agentic.return_value = make_agentic_context()

        response = await client.post("/knowledge/search/agentic", json=AGENTIC_PAYLOAD)

        assert response.status_code == 200
        body = response.json()
        assert body["initial_subqueries"] == ["sub-1", "sub-2"]
        assert body["reasoning"] == "split into parts"
        assert body["degraded_to_hybrid"] is False
        assert body["evidence"] == [
            {
                "query": "sub-1",
                "chunk_id": "chunk-1",
                "score": 0.77,
                "text": "evidence text",
                "metadata": {"source": "book.pdf"},
            }
        ]
        assert body["iterations"] == [
            {
                "iteration": 1,
                "subqueries": ["sub-1", "sub-2"],
                "new_evidence_count": 1,
                "total_evidence_count": 1,
                "evaluation": {
                    "sufficient": False,
                    "coverage": 0.5,
                    "confidence": 0.6,
                    "redundancy": 0.1,
                    "missing_topics": ["auth"],
                    "retry_queries": ["auth in api"],
                },
            }
        ]
        bundle_service.get_bundle.assert_awaited_once_with(1, actor.id)
        service.search_agentic.assert_awaited_once_with(
            query="how to design an api", config_bundle_id=1
        )

    async def test_none_context_returns_empty_response(self, client, service, bundle_service):
        service.search_agentic.return_value = None

        response = await client.post("/knowledge/search/agentic", json=AGENTIC_PAYLOAD)

        assert response.status_code == 200
        assert response.json() == {
            "initial_subqueries": [],
            "reasoning": "",
            "evidence": [],
            "iterations": [],
            "degraded_to_hybrid": False,
        }

    async def test_marks_degraded_when_no_iterations(self, client, service, bundle_service):
        service.search_agentic.return_value = make_agentic_context(with_iterations=False)

        response = await client.post("/knowledge/search/agentic", json=AGENTIC_PAYLOAD)

        body = response.json()
        assert body["degraded_to_hybrid"] is True
        assert body["iterations"] == []
        assert len(body["evidence"]) == 1

    async def test_admin_skips_bundle_check(self, client, service, bundle_service, as_admin):
        service.search_agentic.return_value = None

        response = await client.post("/knowledge/search/agentic", json=AGENTIC_PAYLOAD)

        assert response.status_code == 200
        bundle_service.get_bundle.assert_not_awaited()

    async def test_foreign_bundle_returns_404(self, client, service, bundle_service):
        bundle_service.get_bundle.side_effect = NotFoundError("nf")

        response = await client.post("/knowledge/search/agentic", json=AGENTIC_PAYLOAD)

        assert response.status_code == 404
        service.search_agentic.assert_not_awaited()

    async def test_value_error_returns_400(self, client, service, bundle_service):
        service.search_agentic.side_effect = ValueError("boom")

        response = await client.post("/knowledge/search/agentic", json=AGENTIC_PAYLOAD)

        assert response.status_code == 400
        assert response.json()["detail"] == "boom"

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"query": "q"},
            {"config_bundle_id": 1},
            {**AGENTIC_PAYLOAD, "query": ["x"]},
            {**AGENTIC_PAYLOAD, "config_bundle_id": "abc"},
        ],
    )
    async def test_rejects_invalid_payload(self, client, service, bundle_service, payload):
        response = await client.post("/knowledge/search/agentic", json=payload)

        assert response.status_code == 422
        service.search_agentic.assert_not_awaited()