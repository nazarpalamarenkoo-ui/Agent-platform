import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import pytest

from src.db.enums.document_status import DocumentStatus
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.knowledge.corpus.builder import CorpusBuilder
from src.knowledge.documents_schema.raw_document import RawDocument
from src.knowledge.pipeline import IngestionPipeline

pytestmark = pytest.mark.integration

TECH_TEXT = """
Event sourcing stores the state of a system as an append-only sequence of events instead of
overwriting rows in place. Every change, such as an order being placed or a payment being
captured, is recorded as an immutable fact. The current state is derived by replaying the events
in order, which makes the full history of the system auditable and makes it possible to rebuild
read models at any time.

The main trade-off is complexity. Queries against a raw event log are slow, so production
systems maintain projections that are updated asynchronously. This means read models are
eventually consistent, and the application must be designed to tolerate stale reads. Snapshots
are used to avoid replaying millions of events for long-lived aggregates, and schema evolution
requires explicit upcasting of old events when their structure changes.

In practice a team adopting event sourcing should decide how events are versioned, how
idempotent consumers handle duplicate delivery, and how to repair a projection that was built with
a bug. A common approach is to store events in a relational database with an optimistic
concurrency check on the aggregate version, publish them through a transactional outbox, and
rebuild projections by replaying the stream into a fresh table before switching traffic over.
Operational concerns such as retention, GDPR deletion through crypto-shredding, and monitoring of
projection lag are as important as the modelling itself, and they are usually underestimated
during the first iteration of the design.
""" * 2

OTHER_TEXT = """
Command query responsibility segregation separates the model used to change state from the model
used to read it. Commands express intent, such as reserving a seat or cancelling a subscription,
and are validated against the write model, while queries are served from denormalised views that
are shaped around the screens and reports that consume them. This split lets each side be scaled,
cached and evolved independently.

The cost of the pattern is operational and cognitive. Two models must be kept in sync, usually
through asynchronous messaging, so the read side lags behind the write side and users may briefly
see outdated data. Teams must decide how to surface that delay in the interface, how to deal with
poison messages that block a projection, and how to replay a view after a defect has been fixed.

Practical guidance is to apply the pattern only to the bounded contexts that genuinely need
different read and write characteristics. A simple CRUD module rarely benefits. Where it does
apply, keep commands small and explicit, make handlers idempotent, version message contracts from
the first release, and track consumer lag and dead-letter volume as first-class service level
indicators so that regressions in the read model are noticed before customers report them.
""" * 2

SOURCE = "https://example.com/event-sourcing.txt"


class FakeDocumentRepo:
    def __init__(self):
        self.docs = {}
        self._next_id = 1
        self.status_history = []
        self.fail_on_status = None

    async def create(self, **kwargs):
        doc = SimpleNamespace(id=self._next_id, status=DocumentStatus.PENDING, **kwargs)
        self.docs[doc.id] = doc
        self._next_id += 1
        return doc

    async def get_by_hash(self, content_hash):
        return next((d for d in self.docs.values() if d.content_hash == content_hash), None)

    async def update_status(self, document_id, status):
        if self.fail_on_status == status:
            raise RuntimeError(f"db failed on status {status}")
        self.docs[document_id].status = status
        self.status_history.append((document_id, status))


class FakeChunkRepo:
    def __init__(self):
        self.rows = []
        self.fail = None

    async def bulk_create(self, rows):
        if self.fail:
            raise self.fail
        self.rows.extend(rows)


class FakeVectorStore:
    def __init__(self):
        self.points = {}
        self.upsert_error = None
        self.delete_error_on_call = None
        self.delete_calls = 0

    async def upsert_batch(self, points):
        if self.upsert_error:
            raise self.upsert_error
        for p in points:
            self.points[p.id] = p

    async def delete(self, point_id):
        self.delete_calls += 1
        if self.delete_error_on_call == self.delete_calls:
            raise RuntimeError("qdrant delete failed")
        self.points.pop(point_id, None)


class FakePackRepo:
    def __init__(self):
        self.packs = {
            1: SimpleNamespace(slug="event-sourcing-pack", domain=SimpleNamespace(slug="backend-architecture"))
        }

    async def get_by_id(self, pack_id):
        return self.packs.get(pack_id)


class FakeEmbedder:
    def __init__(self):
        self.error = None
        self.drop_last = False
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.error:
            raise self.error
        results = [
            SimpleNamespace(
                dense=SimpleNamespace(values=[0.1, 0.2, 0.3]),
                sparse=SimpleNamespace(indices=[0, 1], values=[0.5, 0.2]),
            )
            for _ in texts
        ]
        return results[:-1] if self.drop_last else results


def make_raw(content=None, content_type="text/plain", source=SOURCE):
    if content is None:
        content = TECH_TEXT.encode()
    if isinstance(content, str):
        content = content.encode()
    return RawDocument(
        source=source,
        content=content,
        content_type=content_type,
        content_hash=hashlib.sha256(content).hexdigest(),
        fetched_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )


def make_pdf_bytes(text=TECH_TEXT) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 555, 800), text[:3000], fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def env():
    e = SimpleNamespace(
        vector_store=FakeVectorStore(),
        document_repo=FakeDocumentRepo(),
        chunk_repo=FakeChunkRepo(),
        pack_repo=FakePackRepo(),
        embedder=FakeEmbedder(),
    )
    with patch("src.knowledge.pipeline.Embedding", return_value=e.embedder):
        e.pipeline = IngestionPipeline(
            vector_store=e.vector_store,
            document_repo=e.document_repo,
            chunk_repo=e.chunk_repo,
            pack_repo=e.pack_repo,
        )
    return e


async def run(env, raw=None, doc_type=DocumentType.BLOG_POST, k_type=KnowledgeType.REFERENCE, pack_id=1):
    return await env.pipeline.process(raw or make_raw(), doc_type, k_type, pack_id)


def assert_nothing_persisted(env):
    assert env.document_repo.docs == {}
    assert env.chunk_repo.rows == []
    assert env.vector_store.points == {}


class TestPipelineEndToEnd:

    @pytest.mark.asyncio
    async def test_plain_text_is_fully_indexed(self, env):
        document = await run(env)

        assert env.document_repo.docs[document.id].status == DocumentStatus.INDEXED
        assert len(env.vector_store.points) > 0
        assert len(env.chunk_repo.rows) == len(env.vector_store.points)
        assert env.document_repo.status_history == [(document.id, DocumentStatus.INDEXED)]

    @pytest.mark.asyncio
    async def test_document_row_contains_raw_document_metadata(self, env):
        raw = make_raw()

        document = await run(env, raw, DocumentType.PAPER, KnowledgeType.PRINCIPLE)

        assert document.source == SOURCE
        assert document.content_hash == raw.content_hash
        assert document.size == len(raw.content)
        assert document.embedding_model == "BAAI/bge-m3"
        assert document.knowledge_pack_id == 1
        assert document.document_type == DocumentType.PAPER
        assert document.knowledge_type == KnowledgeType.PRINCIPLE

    @pytest.mark.asyncio
    async def test_chunk_rows_reference_existing_vector_points(self, env):
        document = await run(env)

        for row in env.chunk_repo.rows:
            assert row["document_id"] == document.id
            assert row["qdrant_point_id"] in env.vector_store.points
            assert row["token_count"] > 0
        indexes = [r["chunk_index"] for r in env.chunk_repo.rows]
        assert len(indexes) == len(set(indexes))

    @pytest.mark.asyncio
    async def test_payload_and_point_ids_are_built_correctly(self, env):
        document = await run(env, doc_type=DocumentType.BOOK)

        for point in env.vector_store.points.values():
            payload = point.payload
            expected_id = hashlib.md5(
                f"{document.id}:{payload['chunk_index']}:{payload['text']}".encode()
            ).hexdigest()
            assert point.id == expected_id
            assert payload["document_id"] == document.id
            assert payload["knowledge_pack"] == "event-sourcing-pack"
            assert payload["domain"] == "backend-architecture"
            assert payload["source_type"] == DocumentType.BOOK.value
            assert isinstance(payload["language"], str) and payload["language"]
            assert isinstance(payload["tags"], list)
            assert 0.0 <= payload["quality_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_embedder_receives_exactly_the_chunk_texts(self, env):
        await run(env)

        sent = env.embedder.calls[0]
        stored = {p.payload["text"] for p in env.vector_store.points.values()}
        assert set(sent) == stored

    @pytest.mark.asyncio
    async def test_html_document_is_extracted_and_indexed(self, env):
        paragraphs = "".join(f"<p>{p}</p>" for p in TECH_TEXT.split("\n\n") if p.strip())
        html = f"<html><body><h1>Event sourcing</h1>{paragraphs}</body></html>"

        document = await run(env, make_raw(html, "text/html", "https://example.com/es"))

        assert env.document_repo.docs[document.id].status == DocumentStatus.INDEXED
        assert env.vector_store.points

    @pytest.mark.asyncio
    async def test_pdf_document_is_extracted_and_indexed(self, env):
        raw = make_raw(make_pdf_bytes(), "application/pdf", "https://example.com/es.pdf")

        document = await run(env, raw)

        assert env.document_repo.docs[document.id].status == DocumentStatus.INDEXED
        assert env.vector_store.points

    @pytest.mark.asyncio
    async def test_different_documents_get_separate_points(self, env):
        first = await run(env)
        first_point_ids = set(env.vector_store.points)

        second = await run(env, make_raw(OTHER_TEXT, source="https://example.com/cqrs.txt"))

        assert first.id != second.id
        second_point_ids = set(env.vector_store.points) - first_point_ids
        assert second_point_ids
        assert {env.vector_store.points[i].payload["document_id"] for i in second_point_ids} == {second.id}
        assert {env.vector_store.points[i].payload["document_id"] for i in first_point_ids} == {first.id}


class TestPipelineFailsBeforePersistence:

    @pytest.mark.asyncio
    async def test_unknown_pack(self, env):
        with pytest.raises(ValueError, match="does not exist"):
            await run(env, pack_id=999)

        assert_nothing_persisted(env)

    @pytest.mark.asyncio
    async def test_unsupported_content_type(self, env):
        with pytest.raises(Exception):
            await run(env, make_raw(b"PK\x03\x04", "application/zip"))

        assert_nothing_persisted(env)

    @pytest.mark.asyncio
    async def test_corrupt_pdf(self, env):
        with pytest.raises(Exception):
            await run(env, make_raw(b"%PDF-1.7 definitely not a pdf", "application/pdf"))

        assert_nothing_persisted(env)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("content", [b"", b"   \n\n  ", b"ok"])
    async def test_empty_or_trivial_content_yields_no_chunks(self, env, content):
        with pytest.raises(ValueError):
            await run(env, make_raw(content))

        assert_nothing_persisted(env)

    @pytest.mark.asyncio
    async def test_boilerplate_only_document_is_rejected(self, env):
        spam = "Subscribe to our newsletter. Accept all cookies. " * 3

        with pytest.raises(ValueError):
            await run(env, make_raw(spam))

        assert_nothing_persisted(env)


class TestPipelineFailureAfterDocumentCreated:

    @pytest.mark.asyncio
    async def test_embedder_failure_marks_document_failed(self, env):
        env.embedder.error = RuntimeError("embedding service down")

        with pytest.raises(RuntimeError, match="embedding service down"):
            await run(env)

        assert env.document_repo.docs[1].status == DocumentStatus.FAILED
        assert env.vector_store.points == {}
        assert env.chunk_repo.rows == []

    @pytest.mark.asyncio
    async def test_qdrant_upsert_failure_marks_failed_without_rollback(self, env):
        env.vector_store.upsert_error = ConnectionError("qdrant unreachable")

        with pytest.raises(ConnectionError):
            await run(env)

        assert env.document_repo.docs[1].status == DocumentStatus.FAILED
        assert env.vector_store.delete_calls == 0
        assert env.chunk_repo.rows == []

    @pytest.mark.asyncio
    async def test_chunk_repo_failure_rolls_back_all_vectors(self, env):
        env.chunk_repo.fail = RuntimeError("db write failed")

        with pytest.raises(RuntimeError, match="db write failed"):
            await run(env)

        assert env.document_repo.docs[1].status == DocumentStatus.FAILED
        assert env.vector_store.points == {}
        assert env.vector_store.delete_calls > 0

    @pytest.mark.asyncio
    async def test_failure_when_marking_indexed_rolls_back_and_marks_failed(self, env):
        env.document_repo.fail_on_status = DocumentStatus.INDEXED

        with pytest.raises(RuntimeError, match="db failed on status"):
            await run(env)

        assert env.document_repo.docs[1].status != DocumentStatus.INDEXED
        assert env.vector_store.points == {}

    @pytest.mark.asyncio
    async def test_failed_document_does_not_leave_chunk_rows(self, env):
        env.chunk_repo.fail = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await run(env)

        assert env.chunk_repo.rows == []

    @pytest.mark.asyncio
    async def test_one_failure_does_not_poison_next_run(self, env):
        env.embedder.error = RuntimeError("down")
        with pytest.raises(RuntimeError):
            await run(env)
        env.embedder.error = None

        document = await run(env, make_raw(TECH_TEXT + " extra", source="https://example.com/other"))

        assert env.document_repo.docs[document.id].status == DocumentStatus.INDEXED

    @pytest.mark.asyncio
    async def test_rollback_continues_and_preserves_original_error_when_delete_fails(self, env):
        env.chunk_repo.fail = RuntimeError("db write failed")
        env.vector_store.delete_error_on_call = 1

        with pytest.raises(RuntimeError, match="db write failed"):
            await run(env)

        assert env.document_repo.docs[1].status == DocumentStatus.FAILED
        assert env.vector_store.delete_calls >= 1
        assert len(env.vector_store.points) == 1

    @pytest.mark.asyncio
    async def test_embedding_count_mismatch_must_fail(self, env):
        env.embedder.drop_last = True

        with pytest.raises(ValueError, match="Embedder returned"):
            await run(env)

        assert env.document_repo.docs[1].status == DocumentStatus.FAILED
        assert env.vector_store.points == {}
        assert env.chunk_repo.rows == []
        
class LocalFileLoader:

    def __init__(self, content_type):
        self.content_type = content_type

    def load_document(self, path):
        with open(path, "rb") as f:
            content = f.read()
        return RawDocument(
            source=path,
            content=content,
            content_type=self.content_type,
            content_hash=hashlib.sha256(content).hexdigest(),
            fetched_at=datetime.now(timezone.utc),
        )


@pytest.fixture
def builder(env):
    return CorpusBuilder(pipeline=env.pipeline, orchestrator=MagicMock(), document_repo=env.document_repo)


class TestCorpusBuilderWithRealPipeline:

    @pytest.fixture(autouse=True)
    def local_loaders(self):
        with patch(
            "src.knowledge.ingestion.loaders.registry.LoaderRegistry.create",
            side_effect=lambda content_type: LocalFileLoader(content_type),
        ):
            yield

    @pytest.mark.asyncio
    async def test_build_from_path_indexes_text_file(self, builder, env, tmp_path):
        path = tmp_path / "es.txt"
        path.write_text(TECH_TEXT, encoding="utf-8")

        result = await builder.build_from_path([str(path)], 1, DocumentType.BLOG_POST, KnowledgeType.REFERENCE)

        assert len(result.succeeded) == 1
        assert result.failed == []
        assert env.vector_store.points

    @pytest.mark.asyncio
    async def test_second_run_with_same_file_is_skipped_as_duplicate(self, builder, env, tmp_path):
        path = tmp_path / "es.txt"
        path.write_text(TECH_TEXT, encoding="utf-8")
        args = ([str(path)], 1, DocumentType.BLOG_POST, KnowledgeType.REFERENCE)
        await builder.build_from_path(*args)
        points_before = len(env.vector_store.points)

        result = await builder.build_from_path(*args)

        assert result.succeeded == []
        assert result.skipped_duplicates == [str(path)]
        assert len(env.vector_store.points) == points_before

    @pytest.mark.asyncio
    async def test_bad_and_good_files_in_one_batch(self, builder, env, tmp_path):
        good = tmp_path / "good.txt"
        good.write_text(TECH_TEXT, encoding="utf-8")
        empty = tmp_path / "empty.txt"
        empty.write_text("", encoding="utf-8")
        missing = tmp_path / "missing.txt"
        unknown = tmp_path / "noext"
        unknown.write_text("x")

        result = await builder.build_from_path(
            [str(good), str(empty), str(missing), str(unknown)],
            1, DocumentType.BLOG_POST, KnowledgeType.REFERENCE,
        )

        assert len(result.succeeded) == 1
        failed_sources = {f["source"] for f in result.failed}
        assert str(missing) in failed_sources
        assert str(unknown) in failed_sources
        assert str(empty) in failed_sources

    @pytest.mark.asyncio
    async def test_build_from_search_processes_orchestrator_output(self, builder, env):
        builder.orchestrator.orchestrate = AsyncMock(return_value=[
            make_raw(TECH_TEXT, "text/plain", "https://a.com/x"),
            make_raw(b"x", "text/plain", "https://b.com/y"),
        ])

        result = await builder.build_from_search("event sourcing", 1, DocumentType.BLOG_POST, KnowledgeType.REFERENCE)

        assert len(result.succeeded) == 1
        assert [f["source"] for f in result.failed] == ["https://b.com/y"]
        builder.orchestrator.orchestrate.assert_awaited_once_with("event sourcing")

    @pytest.mark.asyncio
    async def test_infrastructure_failure_is_reported_not_raised(self, builder, env, tmp_path):
        env.vector_store.upsert_error = ConnectionError("qdrant unreachable")
        path = tmp_path / "es.txt"
        path.write_text(TECH_TEXT, encoding="utf-8")

        result = await builder.build_from_path([str(path)], 1, DocumentType.BLOG_POST, KnowledgeType.REFERENCE)

        assert result.succeeded == []
        assert result.failed == [{"source": str(path), "error": "qdrant unreachable"}]