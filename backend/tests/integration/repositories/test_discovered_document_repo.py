import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.db.enums.discovery_type import DiscoveredDocumentDecision
from src.db.models.discovered_document import DiscoveredDocument
from src.knowledge.acquisition.dedup.deduplicator import Deduplicator
from src.knowledge.acquisition.dedup.url_normalizer import calculate_hash_from_url
from src.knowledge.acquisition.judge.judge_persistence import JudgePersistence
from src.knowledge.acquisition.judge.models import (
    DecidedSource,
    DocumentDecision,
    JudgeSource,
    TrustBreakdown,
)
from src.knowledge.documents_schema.discovery_model import DiscoveryResult
from src.repositories.discovered_document_repo import DiscoveredDocumentRepository
from src.schemas.discovered_document import DiscoveredDocumentCreate

pytestmark = pytest.mark.db


def make_record(
    url="https://example.com/a",
    decision=DiscoveredDocumentDecision.ACCEPT,
    trust_score=0.8,
    educational=0.9,
    implementation=0.7,
    authority=0.6,
    category="tutorial",
    reason="Walks through projections and snapshots with a worked example.",
):
    return DiscoveredDocumentCreate(
        url=url,
        url_hash=calculate_hash_from_url(url),
        decision=decision,
        trust_score=trust_score,
        educational_score=educational,
        implementation_score=implementation,
        authority_score=authority,
        document_category=category,
        reason=reason,
    )


def make_discovery(url):
    return DiscoveryResult(
        title="t", url=url, domain="example.com", snippet="s", mime_type="text/html"
    )


def make_decided(url, decision=DocumentDecision.ACCEPT, score=0.8, category="tutorial"):
    source = JudgeSource(
        key=f"key-{url}",
        url=url,
        title="t",
        trust=TrustBreakdown(educational=0.9, implementation=0.7, authority=0.5),
        document_category=category,
        reason="specific reason",
    )
    return DecidedSource(source=source, decision=decision, overall_score=score)


async def count_rows(session) -> int:
    result = await session.execute(select(func.count()).select_from(DiscoveredDocument))
    return result.scalar_one()


@pytest.fixture
def discovered_repo(db_session):
    return DiscoveredDocumentRepository(db_session)


class TestGetExistingUrlHashes:

    async def test_empty_input_returns_empty_set(self, discovered_repo):
        assert await discovered_repo.get_existing_url_hashes([]) == set()

    async def test_unknown_hashes_return_empty_set(self, discovered_repo):
        hashes = [calculate_hash_from_url(f"https://unknown.com/{i}") for i in range(3)]

        assert await discovered_repo.get_existing_url_hashes(hashes) == set()

    async def test_returns_only_hashes_that_exist(self, discovered_repo):
        known = make_record("https://known.com/a")
        await discovered_repo.save_all([known])
        unknown_hash = calculate_hash_from_url("https://unknown.com/a")

        result = await discovered_repo.get_existing_url_hashes([known.url_hash, unknown_hash])

        assert result == {known.url_hash}

    async def test_returns_a_set_of_strings(self, discovered_repo):
        record = make_record()
        await discovered_repo.save_all([record])

        result = await discovered_repo.get_existing_url_hashes([record.url_hash])

        assert isinstance(result, set)
        assert all(isinstance(h, str) for h in result)

    async def test_duplicate_input_hashes_are_collapsed(self, discovered_repo):
        record = make_record()
        await discovered_repo.save_all([record])

        result = await discovered_repo.get_existing_url_hashes([record.url_hash, record.url_hash])

        assert result == {record.url_hash}

    async def test_handles_large_input_lists(self, discovered_repo):
        records = [make_record(f"https://bulk.com/{i}") for i in range(20)]
        await discovered_repo.save_all(records)
        queried = [r.url_hash for r in records] + [
            calculate_hash_from_url(f"https://missing.com/{i}") for i in range(1000)
        ]

        result = await discovered_repo.get_existing_url_hashes(queried)

        assert result == {r.url_hash for r in records}

    async def test_rejected_documents_are_also_reported_as_existing(self, discovered_repo):
        record = make_record(decision=DiscoveredDocumentDecision.REJECT, trust_score=0.2)
        await discovered_repo.save_all([record])

        assert await discovered_repo.get_existing_url_hashes([record.url_hash]) == {record.url_hash}


class TestSaveAll:

    async def test_empty_list_is_a_noop(self, discovered_repo, db_session):
        await discovered_repo.save_all([])

        assert await count_rows(db_session) == 0

    async def test_persists_every_field(self, discovered_repo, db_session):
        record = make_record(
            url="https://docs.example.com/guide",
            decision=DiscoveredDocumentDecision.ACCEPT,
            trust_score=0.825,
            educational=0.9,
            implementation=0.8,
            authority=0.7,
            category="official_docs",
            reason="Headings cover snapshots and upcasting.",
        )

        await discovered_repo.save_all([record])

        result = await db_session.execute(
            select(DiscoveredDocument).where(DiscoveredDocument.url_hash == record.url_hash)
        )
        row = result.scalar_one()
        assert row.id is not None
        assert row.url == "https://docs.example.com/guide"
        assert row.decision == DiscoveredDocumentDecision.ACCEPT
        assert row.trust_score == pytest.approx(0.825)
        assert row.educational_score == pytest.approx(0.9)
        assert row.implementation_score == pytest.approx(0.8)
        assert row.authority_score == pytest.approx(0.7)
        assert row.document_category == "official_docs"
        assert row.reason == "Headings cover snapshots and upcasting."

    async def test_persists_multiple_records_in_one_call(self, discovered_repo, db_session):
        records = [make_record(f"https://multi.com/{i}") for i in range(5)]

        await discovered_repo.save_all(records)

        assert await count_rows(db_session) == 5

    async def test_persists_both_decisions(self, discovered_repo, db_session):
        accepted = make_record("https://a.com", DiscoveredDocumentDecision.ACCEPT, 0.9)
        rejected = make_record("https://b.com", DiscoveredDocumentDecision.REJECT, 0.1)

        await discovered_repo.save_all([accepted, rejected])

        result = await db_session.execute(select(DiscoveredDocument.url, DiscoveredDocument.decision))
        decisions = {url: decision for url, decision in result.all()}
        assert decisions == {
            "https://a.com": DiscoveredDocumentDecision.ACCEPT,
            "https://b.com": DiscoveredDocumentDecision.REJECT,
        }

    @pytest.mark.parametrize("score", [0.0, 1.0])
    async def test_score_boundaries_are_stored(self, discovered_repo, db_session, score):
        record = make_record(
            trust_score=score, educational=score, implementation=score, authority=score
        )

        await discovered_repo.save_all([record])

        row = (await db_session.execute(select(DiscoveredDocument))).scalar_one()
        assert row.trust_score == pytest.approx(score)
        assert row.authority_score == pytest.approx(score)

    async def test_duplicate_url_hash_raises_integrity_error(self, discovered_repo, db_session):
        await discovered_repo.save_all([make_record("https://dup.com/a")])
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await discovered_repo.save_all([make_record("https://dup.com/a")])
            await db_session.commit()

        await db_session.rollback()

    async def test_duplicate_url_hash_within_one_batch_raises_integrity_error(
        self, discovered_repo, db_session
    ):
        with pytest.raises(IntegrityError):
            await discovered_repo.save_all([make_record("https://dup.com/b"), make_record("https://dup.com/b")])
            await db_session.commit()

        await db_session.rollback()

    async def test_failed_batch_does_not_persist_valid_records(self, discovered_repo, db_session):
        await discovered_repo.save_all([make_record("https://existing.com")])
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await discovered_repo.save_all([make_record("https://fresh.com"), make_record("https://existing.com")])
            await db_session.commit()
        await db_session.rollback()

        assert await discovered_repo.get_existing_url_hashes(
            [calculate_hash_from_url("https://fresh.com")]
        ) == set()

    async def test_save_all_flushes_but_does_not_commit(self, discovered_repo, db_session):
        record = make_record("https://uncommitted.com")

        await discovered_repo.save_all([record])
        assert await discovered_repo.get_existing_url_hashes([record.url_hash]) == {record.url_hash}

        await db_session.rollback()

        assert await discovered_repo.get_existing_url_hashes([record.url_hash]) == set()


class TestJudgePersistenceAndDeduplicatorRoundTrip:

    @pytest.fixture
    def persistence(self, discovered_repo):
        return JudgePersistence(discovered_repo)

    @pytest.fixture
    def deduplicator(self, discovered_repo):
        return Deduplicator(discovered_repo)

    async def test_saved_decisions_are_removed_by_deduplicator_on_next_run(
        self, persistence, deduplicator, db_session
    ):
        await persistence.save([
            make_decided("https://accepted.com/a", DocumentDecision.ACCEPT, 0.9),
            make_decided("https://rejected.com/b", DocumentDecision.REJECT, 0.2),
        ])
        candidates = [
            make_discovery("https://accepted.com/a"),
            make_discovery("https://rejected.com/b"),
            make_discovery("https://brand-new.com/c"),
        ]

        remaining = await deduplicator.remove_duplicates(candidates)

        assert [c.url for c in remaining] == ["https://brand-new.com/c"]

    async def test_equivalent_url_variants_are_detected_as_known(
        self, persistence, deduplicator
    ):
        await persistence.save([make_decided("http://www.example.com/page/")])

        remaining = await deduplicator.remove_duplicates([make_discovery("https://example.com/page")])

        assert remaining == []

    async def test_judge_errors_are_not_persisted_and_can_be_retried(
        self, persistence, deduplicator, db_session
    ):
        await persistence.save([
            make_decided("https://flaky.com/a", DocumentDecision.REJECT, 0.0, category="judge_error"),
        ])

        remaining = await deduplicator.remove_duplicates([make_discovery("https://flaky.com/a")])

        assert await count_rows(db_session) == 0
        assert [c.url for c in remaining] == ["https://flaky.com/a"]

    async def test_saving_same_url_twice_through_persistence_raises(
        self, persistence, db_session
    ):
        await persistence.save([make_decided("https://twice.com/a")])
        await db_session.commit()

        with pytest.raises(IntegrityError):
            await persistence.save([make_decided("https://twice.com/a")])
            await db_session.commit()

        await db_session.rollback()

    async def test_deduplicator_handles_empty_candidate_list(self, deduplicator):
        assert await deduplicator.remove_duplicates([]) == []