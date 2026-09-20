from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.routers import knowledge
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.dependencies import get_knowledge_service
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.document_repo import DocumentRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.tag_repo import TagRepository
from src.services.knowledge_service import KnowledgeService

pytestmark = [pytest.mark.integration, pytest.mark.db]

SEARCH_QUERY = {"query": "api design", "limit": 10, "top_n": 5, "k": 60}


@pytest.fixture
def orchestrator():
    return AsyncMock()


@pytest.fixture
def pipeline():
    return AsyncMock()


@pytest.fixture
def retrieval():
    return AsyncMock()


@pytest.fixture
def loader_registry(monkeypatch):
    registry = MagicMock()
    monkeypatch.setattr("src.services.knowledge_service.LoaderRegistry", registry)
    return registry


@pytest.fixture
def app(db_session, build_app, orchestrator, pipeline, retrieval):
    service = KnowledgeService(
        orchestrator=orchestrator,
        ingestion_pipeline=pipeline,
        retrieval=retrieval,
        document_repo=DocumentRepository(db_session),
        tag_repo=TagRepository(db_session),
        knowledge_domain_repo=KnowledgeDomainRepository(db_session),
        config_bundle_repo=ConfigBundleRepository(db_session),
    )
    application = build_app(knowledge.router)
    application.dependency_overrides[get_knowledge_service] = lambda: service
    return application


def file_payload(pack_id, **overrides):
    payload = {
        "source": "/data/book.pdf",
        "document_type": DocumentType.BOOK.value,
        "knowledge_type": KnowledgeType.REFERENCE.value,
        "knowledge_pack_id": pack_id,
    }
    payload.update(overrides)
    return payload


def web_payload(pack_id, **overrides):
    payload = {
        "query": "fastapi",
        "limit": 4,
        "document_type": DocumentType.BOOK.value,
        "knowledge_type": KnowledgeType.REFERENCE.value,
        "knowledge_pack_id": pack_id,
    }
    payload.update(overrides)
    return payload


def make_raw_doc(content_hash, source="https://example.com/raw"):
    return SimpleNamespace(content_hash=content_hash, source=source)


async def test_search_filters_by_knowledge_packs_of_bundle(
    client, retrieval, config_bundle_with_knowledge_pack, sample_knowledge_pack
):
    retrieval.retrieve.return_value = [SimpleNamespace(id="point-1", score=0.8, payload={"text": "chunk"})]

    response = await client.post(
        "/knowledge/search",
        json={**SEARCH_QUERY, "config_bundle_id": config_bundle_with_knowledge_pack.id},
    )

    assert response.status_code == 200
    assert response.json() == [{"id": "point-1", "score": 0.8, "payload": {"text": "chunk"}}]
    retrieval.retrieve.assert_awaited_once()
    args = retrieval.retrieve.await_args.args
    assert args[:4] == ("api design", 10, 5, 60)
    assert args[4].knowledge_packs == [sample_knowledge_pack.slug]


async def test_search_bundle_without_packs_returns_empty_list(client, retrieval, sample_config_bundle):
    response = await client.post(
        "/knowledge/search", json={**SEARCH_QUERY, "config_bundle_id": sample_config_bundle.id}
    )

    assert response.status_code == 200
    assert response.json() == []
    retrieval.retrieve.assert_not_awaited()


async def test_search_unknown_bundle_returns_400(client, retrieval):
    response = await client.post("/knowledge/search", json={**SEARCH_QUERY, "config_bundle_id": 999999})

    assert response.status_code == 400
    assert "999999" in response.json()["detail"]
    retrieval.retrieve.assert_not_awaited()


async def test_ingest_file_new_document_goes_through_pipeline(
    client, pipeline, loader_registry, sample_document, sample_knowledge_pack
):
    raw_doc = make_raw_doc("c" * 64)
    loader_registry.create.return_value.load_document.return_value = raw_doc
    pipeline.process.return_value = sample_document

    response = await client.post("/knowledge/ingest/file", json=file_payload(sample_knowledge_pack.id))

    assert response.status_code == 201
    assert response.json()["id"] == sample_document.id
    pipeline.process.assert_awaited_once_with(
        raw_doc, DocumentType.BOOK, KnowledgeType.REFERENCE, sample_knowledge_pack.id
    )


async def test_ingest_file_existing_hash_returns_existing_document(
    client, pipeline, loader_registry, classified_document, sample_knowledge_pack
):
    loader_registry.create.return_value.load_document.return_value = make_raw_doc(classified_document.content_hash)

    response = await client.post("/knowledge/ingest/file", json=file_payload(sample_knowledge_pack.id))

    assert response.status_code == 201
    assert response.json()["id"] == classified_document.id
    pipeline.process.assert_not_awaited()


async def test_ingest_file_missing_file_returns_404(client, loader_registry, sample_knowledge_pack):
    loader_registry.create.return_value.load_document.side_effect = FileNotFoundError("/data/book.pdf")

    response = await client.post("/knowledge/ingest/file", json=file_payload(sample_knowledge_pack.id))

    assert response.status_code == 404


async def test_ingest_file_unsupported_type_returns_400(client, loader_registry, sample_knowledge_pack):
    loader_registry.create.side_effect = ValueError("Unsupported mime type")

    response = await client.post("/knowledge/ingest/file", json=file_payload(sample_knowledge_pack.id))

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported mime type"


async def test_ingest_from_web_skips_duplicates_and_failed_documents(
    client, orchestrator, pipeline, classified_document, sample_document, sample_knowledge_pack
):
    orchestrator.orchestrate.return_value = [
        make_raw_doc(classified_document.content_hash),
        make_raw_doc("d" * 64),
        make_raw_doc("e" * 64),
        make_raw_doc("f" * 64),
    ]

    async def process(raw_doc, *args):
        if raw_doc.content_hash == "d" * 64:
            return sample_document
        if raw_doc.content_hash == "e" * 64:
            raise ValueError("invalid document")
        raise RuntimeError("pipeline crashed")

    pipeline.process.side_effect = process

    response = await client.post("/knowledge/ingest/web", json=web_payload(sample_knowledge_pack.id))

    assert response.status_code == 201
    assert [item["id"] for item in response.json()] == [sample_document.id]
    orchestrator.orchestrate.assert_awaited_once_with("fastapi", 4)
    assert pipeline.process.await_count == 3


async def test_ingest_from_web_with_no_results_returns_empty_list(
    client, orchestrator, pipeline, sample_knowledge_pack
):
    orchestrator.orchestrate.return_value = []

    response = await client.post("/knowledge/ingest/web", json=web_payload(sample_knowledge_pack.id))

    assert response.status_code == 201
    assert response.json() == []
    pipeline.process.assert_not_awaited()


async def test_ingest_from_web_orchestrator_failure_returns_500(client, orchestrator, sample_knowledge_pack):
    orchestrator.orchestrate.side_effect = RuntimeError("search provider down")

    response = await client.post("/knowledge/ingest/web", json=web_payload(sample_knowledge_pack.id))

    assert response.status_code == 500
    assert response.json()["detail"] == "search provider down"
