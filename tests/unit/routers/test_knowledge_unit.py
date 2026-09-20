from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.api.routers import knowledge
from src.db.enums.document_status import DocumentStatus
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.dependencies import get_knowledge_service
from src.services.knowledge_service import KnowledgeService

pytestmark = pytest.mark.unit

ROUTER = knowledge.router
SERVICE_DEPENDENCY = get_knowledge_service
SERVICE_SPEC = KnowledgeService

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)

FILE_PAYLOAD = {
    "source": "/data/book.pdf",
    "document_type": DocumentType.BOOK.value,
    "knowledge_type": KnowledgeType.REFERENCE.value,
    "knowledge_pack_id": 1,
}

WEB_PAYLOAD = {
    "query": "fastapi dependency injection",
    "limit": 3,
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


def make_document(document_id=1, **overrides):
    data = {
        "id": document_id,
        "source": f"https://example.com/doc-{document_id}.pdf",
        "knowledge_pack_id": 1,
        "document_type": DocumentType.BOOK,
        "knowledge_type": KnowledgeType.REFERENCE,
        "size": 1024,
        "content_hash": "a" * 64,
        "version": 1,
        "scraped_at": NOW,
        "status": DocumentStatus.PENDING,
        "embedding_model": "text-embedding-3-large",
        "tags": [],
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_search_result(point_id="point-1", score=0.9, **payload):
    return SimpleNamespace(id=point_id, score=score, payload=payload or {"text": "chunk"})


async def test_ingest_file_returns_201(client, service):
    service.ingest_file.return_value = make_document(4)

    response = await client.post("/knowledge/ingest/file", json=FILE_PAYLOAD)

    assert response.status_code == 201
    assert response.json()["id"] == 4
    service.ingest_file.assert_awaited_once_with(
        source="/data/book.pdf",
        document_type=DocumentType.BOOK,
        knowledge_type=KnowledgeType.REFERENCE,
        knowledge_pack_id=1,
    )


async def test_ingest_file_not_found_returns_404(client, service):
    service.ingest_file.side_effect = FileNotFoundError("/data/book.pdf")

    response = await client.post("/knowledge/ingest/file", json=FILE_PAYLOAD)

    assert response.status_code == 404
    assert "/data/book.pdf" in response.json()["detail"]


async def test_ingest_file_value_error_returns_400(client, service):
    service.ingest_file.side_effect = ValueError("Unsupported mime type")

    response = await client.post("/knowledge/ingest/file", json=FILE_PAYLOAD)

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported mime type"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**FILE_PAYLOAD, "document_type": "not-a-document-type"},
        {**FILE_PAYLOAD, "knowledge_type": "not-a-knowledge-type"},
        {**FILE_PAYLOAD, "knowledge_pack_id": "abc"},
    ],
)
async def test_ingest_file_rejects_invalid_payload(client, service, payload):
    response = await client.post("/knowledge/ingest/file", json=payload)

    assert response.status_code == 422
    service.ingest_file.assert_not_awaited()


async def test_ingest_from_web_returns_201_with_documents(client, service):
    service.ingest_from_web.return_value = [make_document(1), make_document(2)]

    response = await client.post("/knowledge/ingest/web", json=WEB_PAYLOAD)

    assert response.status_code == 201
    assert [item["id"] for item in response.json()] == [1, 2]
    service.ingest_from_web.assert_awaited_once_with(
        query="fastapi dependency injection",
        limit=3,
        document_type=DocumentType.BOOK,
        knowledge_type=KnowledgeType.REFERENCE,
        knowledge_pack_id=1,
    )


async def test_ingest_from_web_returns_empty_list(client, service):
    service.ingest_from_web.return_value = []

    response = await client.post("/knowledge/ingest/web", json=WEB_PAYLOAD)

    assert response.status_code == 201
    assert response.json() == []


async def test_ingest_from_web_unexpected_error_returns_500(client, service):
    service.ingest_from_web.side_effect = RuntimeError("upstream failed")

    response = await client.post("/knowledge/ingest/web", json=WEB_PAYLOAD)

    assert response.status_code == 500
    assert response.json()["detail"] == "upstream failed"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**WEB_PAYLOAD, "limit": "many"},
        {**WEB_PAYLOAD, "document_type": "not-a-document-type"},
        {**WEB_PAYLOAD, "query": ["x"]},
    ],
)
async def test_ingest_from_web_rejects_invalid_payload(client, service, payload):
    response = await client.post("/knowledge/ingest/web", json=payload)

    assert response.status_code == 422
    service.ingest_from_web.assert_not_awaited()


async def test_search_returns_results(client, service):
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
    service.search.assert_awaited_once_with(
        query="how to design an api",
        limit=10,
        top_n=5,
        k=60,
        config_bundle_id=1,
    )


async def test_search_returns_empty_list(client, service):
    service.search.return_value = []

    response = await client.post("/knowledge/search", json=SEARCH_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == []


async def test_search_value_error_returns_400(client, service):
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
async def test_search_rejects_invalid_payload(client, service, payload):
    response = await client.post("/knowledge/search", json=payload)

    assert response.status_code == 422
    service.search.assert_not_awaited()
