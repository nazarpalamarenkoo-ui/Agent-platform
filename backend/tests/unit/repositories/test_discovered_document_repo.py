from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.enums.discovery_type import DiscoveredDocumentDecision
from src.db.models.discovered_document import DiscoveredDocument
from src.knowledge.acquisition.dedup.url_normalizer import calculate_hash_from_url
from src.repositories.discovered_document_repo import DiscoveredDocumentRepository
from src.schemas.discovered_document import DiscoveredDocumentCreate


def make_record(
    url="https://example.com/a",
    decision=DiscoveredDocumentDecision.ACCEPT,
    trust_score=0.8,
):
    return DiscoveredDocumentCreate(
        url=url,
        url_hash=calculate_hash_from_url(url),
        decision=decision,
        trust_score=trust_score,
        educational_score=0.9,
        implementation_score=0.7,
        authority_score=0.6,
        document_category="tutorial",
        reason="Walks through projections and snapshots.",
    )


def make_execute_result(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.fixture
def session():
    mock = MagicMock()
    mock.execute = AsyncMock(return_value=make_execute_result([]))
    mock.add_all = MagicMock()
    mock.flush = AsyncMock()
    mock.commit = AsyncMock()
    return mock


@pytest.fixture
def repo(session):
    return DiscoveredDocumentRepository(session)


def compiled_sql(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


class TestInit:

    def test_keeps_session(self, repo, session):
        assert repo.session is session


class TestGetExistingUrlHashes:

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_set_without_querying(self, repo, session):
        result = await repo.get_existing_url_hashes([])

        assert result == set()
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_hashes_from_query_result_as_set(self, repo, session):
        session.execute = AsyncMock(return_value=make_execute_result(["h1", "h2"]))

        result = await repo.get_existing_url_hashes(["h1", "h2", "h3"])

        assert result == {"h1", "h2"}
        assert isinstance(result, set)

    @pytest.mark.asyncio
    async def test_duplicate_rows_are_collapsed(self, repo, session):
        session.execute = AsyncMock(return_value=make_execute_result(["h1", "h1"]))

        assert await repo.get_existing_url_hashes(["h1"]) == {"h1"}

    @pytest.mark.asyncio
    async def test_no_matches_returns_empty_set(self, repo, session):
        session.execute = AsyncMock(return_value=make_execute_result([]))

        assert await repo.get_existing_url_hashes(["h1"]) == set()

    @pytest.mark.asyncio
    async def test_executes_exactly_one_query(self, repo, session):
        await repo.get_existing_url_hashes(["h1", "h2"])

        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_selects_url_hash_filtered_with_in(self, repo, session):
        await repo.get_existing_url_hashes(["abc123", "def456"])

        sql = compiled_sql(session.execute.await_args.args[0])
        assert "url_hash" in sql
        assert "IN" in sql
        assert "'abc123'" in sql
        assert "'def456'" in sql

    @pytest.mark.asyncio
    async def test_database_errors_propagate(self, repo, session):
        session.execute = AsyncMock(side_effect=RuntimeError("db down"))

        with pytest.raises(RuntimeError, match="db down"):
            await repo.get_existing_url_hashes(["h1"])

    @pytest.mark.asyncio
    async def test_does_not_commit(self, repo, session):
        await repo.get_existing_url_hashes(["h1"])

        session.commit.assert_not_called()


class TestSaveAll:

    @pytest.mark.asyncio
    async def test_empty_list_does_nothing(self, repo, session):
        result = await repo.save_all([])

        assert result is None
        session.add_all.assert_not_called()
        session.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_adds_one_entity_per_record(self, repo, session):
        records = [make_record("https://a.com"), make_record("https://b.com")]

        await repo.save_all(records)

        session.add_all.assert_called_once()
        entities = session.add_all.call_args.args[0]
        assert len(entities) == 2
        assert all(isinstance(e, DiscoveredDocument) for e in entities)

    @pytest.mark.asyncio
    async def test_entities_carry_all_record_fields(self, repo, session):
        record = make_record("https://a.com", DiscoveredDocumentDecision.REJECT, 0.25)

        await repo.save_all([record])

        entity = session.add_all.call_args.args[0][0]
        assert entity.url == "https://a.com"
        assert entity.url_hash == record.url_hash
        assert entity.decision == DiscoveredDocumentDecision.REJECT
        assert entity.trust_score == 0.25
        assert entity.educational_score == 0.9
        assert entity.implementation_score == 0.7
        assert entity.authority_score == 0.6
        assert entity.document_category == "tutorial"
        assert entity.reason == "Walks through projections and snapshots."

    @pytest.mark.asyncio
    async def test_preserves_record_order(self, repo, session):
        urls = [f"https://site{i}.com" for i in range(4)]

        await repo.save_all([make_record(u) for u in urls])

        entities = session.add_all.call_args.args[0]
        assert [e.url for e in entities] == urls

    @pytest.mark.asyncio
    async def test_flushes_once_after_adding(self, repo, session):
        calls = []
        session.add_all.side_effect = lambda _entities: calls.append("add_all")
        session.flush.side_effect = lambda: calls.append("flush")

        await repo.save_all([make_record()])

        assert calls == ["add_all", "flush"]
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_commit(self, repo, session):
        await repo.save_all([make_record()])

        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_errors_propagate(self, repo, session):
        session.flush = AsyncMock(side_effect=RuntimeError("constraint violated"))

        with pytest.raises(RuntimeError, match="constraint violated"):
            await repo.save_all([make_record()])