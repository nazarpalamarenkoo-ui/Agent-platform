from unittest.mock import AsyncMock, MagicMock

import pytest

from src.knowledge.acquisition.dedup.deduplicator import Deduplicator
from src.knowledge.acquisition.dedup.url_normalizer import calculate_hash
from src.knowledge.documents_schema.discovery_model import DiscoveryResult
from src.repositories.discovered_document_repo import DiscoveredDocumentRepository


def make_discovery(url):
    return DiscoveryResult(
        title="t", url=url, domain="example.com", snippet="s", mime_type="text/html"
    )


@pytest.fixture
def repo():
    mock = MagicMock(spec=DiscoveredDocumentRepository)
    mock.get_existing_url_hashes = AsyncMock(return_value=set())
    return mock


@pytest.fixture
def deduplicator(repo):
    return Deduplicator(repo)


class TestRemoveDuplicates:

    @pytest.mark.asyncio
    async def test_returns_all_when_nothing_exists(self, deduplicator):
        docs = [make_discovery("https://a.com"), make_discovery("https://b.com")]

        result = await deduplicator.remove_duplicates(docs)

        assert result == docs

    @pytest.mark.asyncio
    async def test_filters_out_existing_documents(self, deduplicator, repo):
        a, b = make_discovery("https://a.com"), make_discovery("https://b.com")
        repo.get_existing_url_hashes = AsyncMock(return_value={calculate_hash(a)})

        result = await deduplicator.remove_duplicates([a, b])

        assert result == [b]

    @pytest.mark.asyncio
    async def test_passes_hashes_in_input_order_to_repo(self, deduplicator, repo):
        a, b = make_discovery("https://a.com"), make_discovery("https://b.com")

        await deduplicator.remove_duplicates([a, b])

        repo.get_existing_url_hashes.assert_awaited_once_with([calculate_hash(a), calculate_hash(b)])

    @pytest.mark.asyncio
    async def test_all_existing_returns_empty_list(self, deduplicator, repo):
        docs = [make_discovery("https://a.com"), make_discovery("https://b.com")]
        repo.get_existing_url_hashes = AsyncMock(return_value={calculate_hash(d) for d in docs})

        assert await deduplicator.remove_duplicates(docs) == []

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_list(self, deduplicator, repo):
        assert await deduplicator.remove_duplicates([]) == []

    @pytest.mark.asyncio
    async def test_matches_equivalent_urls_via_normalization(self, deduplicator, repo):
        existing = make_discovery("http://www.a.com/x/")
        new = make_discovery("https://a.com/x")
        repo.get_existing_url_hashes = AsyncMock(return_value={calculate_hash(existing)})

        assert await deduplicator.remove_duplicates([new]) == []