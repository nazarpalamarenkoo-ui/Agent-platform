from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.enums.discovery_type import DiscoveredDocumentDecision
from src.knowledge.acquisition.dedup.url_normalizer import calculate_hash_from_url
from src.knowledge.acquisition.judge.judge_persistence import JudgePersistence
from src.knowledge.acquisition.judge.models import (
    DecidedSource,
    DocumentDecision,
    JudgeSource,
    TrustBreakdown,
)
from src.repositories.discovered_document_repo import DiscoveredDocumentRepository


def make_decided(
    url="https://example.com/a",
    decision=DocumentDecision.ACCEPT,
    score=0.8,
    category="tutorial",
):
    source = JudgeSource(
        key="k",
        url=url,
        title="t",
        trust=TrustBreakdown(educational=0.9, implementation=0.7, authority=0.5),
        document_category=category,
        reason="because",
    )
    return DecidedSource(source=source, decision=decision, overall_score=score)


@pytest.fixture
def repo():
    mock = MagicMock(spec=DiscoveredDocumentRepository)
    mock.save_all = AsyncMock()
    return mock


@pytest.fixture
def persistence(repo):
    return JudgePersistence(repo)


class TestSave:

    @pytest.mark.asyncio
    async def test_empty_list_does_not_call_repo(self, persistence, repo):
        await persistence.save([])

        repo.save_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_only_judge_errors_does_not_call_repo(self, persistence, repo):
        await persistence.save([make_decided(category="judge_error")])

        repo.save_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_maps_fields_to_record(self, persistence, repo):
        await persistence.save([make_decided(url="https://example.com/a", score=0.812)])

        records = repo.save_all.await_args.args[0]
        assert len(records) == 1
        record = records[0]
        assert record.url == "https://example.com/a"
        assert record.url_hash == calculate_hash_from_url("https://example.com/a")
        assert record.decision == DiscoveredDocumentDecision.ACCEPT
        assert record.trust_score == 0.812
        assert record.educational_score == 0.9
        assert record.implementation_score == 0.7
        assert record.authority_score == 0.5
        assert record.document_category == "tutorial"
        assert record.reason == "because"

    @pytest.mark.asyncio
    async def test_maps_reject_decision(self, persistence, repo):
        await persistence.save([make_decided(decision=DocumentDecision.REJECT, score=0.2)])

        record = repo.save_all.await_args.args[0][0]
        assert record.decision == DiscoveredDocumentDecision.REJECT

    @pytest.mark.asyncio
    async def test_filters_judge_errors_but_saves_the_rest(self, persistence, repo):
        decided = [
            make_decided("https://ok.com"),
            make_decided("https://err.com", decision=DocumentDecision.REJECT, score=0.0, category="judge_error"),
            make_decided("https://rejected.com", decision=DocumentDecision.REJECT, score=0.3),
        ]

        await persistence.save(decided)

        records = repo.save_all.await_args.args[0]
        assert [r.url for r in records] == ["https://ok.com", "https://rejected.com"]

    @pytest.mark.asyncio
    async def test_repo_called_once_for_whole_batch(self, persistence, repo):
        await persistence.save([make_decided(f"https://e.com/{i}") for i in range(3)])

        repo.save_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_repo_errors_propagate(self, persistence, repo):
        repo.save_all = AsyncMock(side_effect=RuntimeError("db down"))

        with pytest.raises(RuntimeError):
            await persistence.save([make_decided()])