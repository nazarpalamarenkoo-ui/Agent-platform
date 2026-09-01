import pytest
from sqlalchemy import select

from src.repositories.token_usage_event_repo import TokenUsageEventRepository
from src.db.models.token_usage_events import TokenUsageEvent

pytestmark = pytest.mark.integration


@pytest.fixture
def token_repo(db_session):
    return TokenUsageEventRepository(db_session)


class TestReportUsagePersistence:

    async def test_report_usage_event_is_persisted(
        self, token_repo, db_session, sample_user
    ):
        event = await token_repo.report_usage(sample_user, tokens_used=500)
        await db_session.commit()

        result = await db_session.execute(
            select(TokenUsageEvent)
            .where(TokenUsageEvent.id == event.id)
            .execution_options(populate_existing=True)
        )
        reloaded = result.scalar_one_or_none()

        assert reloaded is not None
        assert reloaded.tokens_used == 500
        assert reloaded.user_id == sample_user.id

    async def test_report_usage_user_total_is_persisted(
        self, token_repo, db_session, sample_user
    ):
        initial = sample_user.tokens_used
        await token_repo.report_usage(sample_user, tokens_used=300)
        await db_session.commit()

        user_id = sample_user.id
        db_session.expire(sample_user)
        from src.repositories.user_repo import UserRepository
        user_repo = UserRepository(db_session)
        reloaded = await user_repo.get_by_id(user_id)

        assert reloaded.tokens_used == initial + 300

    async def test_multiple_report_usages_accumulate_on_user(
        self, token_repo, db_session, sample_user
    ):
        initial = sample_user.tokens_used
        await token_repo.report_usage(sample_user, tokens_used=100)
        await token_repo.report_usage(sample_user, tokens_used=200)
        await token_repo.report_usage(sample_user, tokens_used=50)
        await db_session.commit()

        user_id = sample_user.id
        db_session.expire(sample_user)
        from src.repositories.user_repo import UserRepository
        user_repo = UserRepository(db_session)
        reloaded = await user_repo.get_by_id(user_id)

        assert reloaded.tokens_used == initial + 350

    async def test_report_usage_with_agent_persisted(
        self, token_repo, db_session, sample_user, sample_agent_profile
    ):
        event = await token_repo.report_usage(
            sample_user, tokens_used=150, agent_id=sample_agent_profile.id
        )
        await db_session.commit()

        result = await db_session.execute(
            select(TokenUsageEvent)
            .where(TokenUsageEvent.id == event.id)
            .execution_options(populate_existing=True)
        )
        reloaded = result.scalar_one()

        assert reloaded.agent_id == sample_agent_profile.id


class TestTokenUsageForeignKeyIntegrity:

    async def test_cannot_report_usage_for_nonexistent_user(
        self, db_session
    ):
        from sqlalchemy.exc import IntegrityError

        # No need to construct a User at all here - we're only checking that
        # the FK on TokenUsageEvent.user_id is enforced. The previous version
        # built a placeholder User via User.__new__(User), which bypasses
        # SQLAlchemy's instrumentation (no _sa_instance_state) and blew up on
        # the very next attribute assignment - and the object was never even
        # used afterwards.
        event = TokenUsageEvent(user_id=999_999, tokens_used=100)
        db_session.add(event)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()


class TestGetTotalUsedConsistency:

    async def test_get_total_used_matches_sum_of_events(
        self, token_repo, db_session, sample_user
    ):
        amounts = [100, 250, 75, 400]
        for amount in amounts:
            await token_repo.report_usage(sample_user, tokens_used=amount)
        await db_session.commit()

        total = await token_repo.get_total_used(sample_user.id)

        assert total >= sum(amounts)

    async def test_get_total_used_is_user_scoped(
        self, token_repo, db_session, sample_user, another_user
    ):
        await token_repo.report_usage(sample_user, tokens_used=1000)
        await token_repo.report_usage(another_user, tokens_used=9999)
        await db_session.commit()

        total = await token_repo.get_total_used(sample_user.id)

        assert total < 9999 + 1000 + 1