import pytest

from src.repositories.token_usage_event_repo import TokenUsageEventRepository

pytestmark = pytest.mark.db


@pytest.fixture
def token_repo(db_session):
    return TokenUsageEventRepository(db_session)


class TestTokenUsageEventRepository:

    async def test_report_usage_creates_event(
        self, token_repo, sample_user
    ):
        event = await token_repo.report_usage(sample_user, tokens_used=200)

        assert event is not None
        assert event.id is not None
        assert event.tokens_used == 200
        assert event.user_id == sample_user.id

    async def test_report_usage_increments_user_tokens(
        self, token_repo, sample_user
    ):
        initial = sample_user.tokens_used
        await token_repo.report_usage(sample_user, tokens_used=300)

        assert sample_user.tokens_used == initial + 300

    async def test_report_usage_with_agent(
        self, token_repo, sample_user, sample_agent_profile
    ):
        event = await token_repo.report_usage(
            sample_user, tokens_used=100, agent_id=sample_agent_profile.id
        )

        assert event.agent_id == sample_agent_profile.id

    async def test_get_usage_for_user_returns_events(
        self, token_repo, sample_token_usage_event, sample_user
    ):
        results = await token_repo.get_usage_for_user(sample_user.id)

        ids = {e.id for e in results}
        assert sample_token_usage_event.id in ids

    async def test_get_usage_for_user_empty_for_unknown(self, token_repo):
        results = await token_repo.get_usage_for_user(999999)

        assert results == []

    async def test_get_total_used_sums_tokens(
        self, token_repo, sample_user
    ):
        await token_repo.report_usage(sample_user, tokens_used=100)
        await token_repo.report_usage(sample_user, tokens_used=250)

        total = await token_repo.get_total_used(sample_user.id)

        assert total >= 350

    async def test_get_total_used_zero_for_unknown_user(self, token_repo):
        total = await token_repo.get_total_used(999999)

        assert total == 0

    async def test_is_limit_exceeded_false_when_under_limit(
        self, token_repo, sample_user
    ):
        sample_user.tokens_used = 0
        sample_user.token_limit = 10_000

        result = await token_repo.is_limit_exceeded(sample_user)

        assert result is False

    async def test_is_limit_exceeded_true_when_at_limit(
        self, token_repo, sample_user
    ):
        sample_user.token_limit = 500
        sample_user.tokens_used = 500

        result = await token_repo.is_limit_exceeded(sample_user)

        assert result is True

    async def test_is_limit_exceeded_true_when_over_limit(
        self, token_repo, sample_user
    ):
        sample_user.token_limit = 100
        sample_user.tokens_used = 999

        result = await token_repo.is_limit_exceeded(sample_user)

        assert result is True