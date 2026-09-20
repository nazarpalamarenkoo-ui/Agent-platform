import pytest

from src.repositories.skill_usage_event_repo import SkillUsageEventRepository

pytestmark = pytest.mark.db


@pytest.fixture
def skill_event_repo(db_session):
    return SkillUsageEventRepository(db_session)


class TestSkillUsageEventRepository:

    async def test_get_for_skill_returns_events(
        self, skill_event_repo, sample_skill_usage_event, sample_skill
    ):
        results = await skill_event_repo.get_for_skill(sample_skill.id)

        ids = {e.id for e in results}
        assert sample_skill_usage_event.id in ids

    async def test_get_for_skill_empty_when_no_events(self, skill_event_repo):
        results = await skill_event_repo.get_for_skill(999999)

        assert results == []

    async def test_get_for_skill_respects_limit(
        self, skill_event_repo, sample_skill, sample_user, sample_config_bundle
    ):
        from src.db.models.skill_usage_events import SkillUsageEvent

        for _ in range(5):
            skill_event_repo.session.add(
                SkillUsageEvent(
                    skill_id=sample_skill.id,
                    user_id=sample_user.id,
                    config_bundle_id=sample_config_bundle.id,
                )
            )
        await skill_event_repo.session.flush()

        results = await skill_event_repo.get_for_skill(sample_skill.id, limit=3)

        assert len(results) <= 3

    async def test_get_for_config_bundle_returns_events(
        self, skill_event_repo, sample_skill_usage_event, sample_config_bundle
    ):
        results = await skill_event_repo.get_for_config_bundle(sample_config_bundle.id)

        ids = {e.id for e in results}
        assert sample_skill_usage_event.id in ids

    async def test_get_for_config_bundle_loads_skill_relation(
        self, skill_event_repo, sample_skill_usage_event, sample_config_bundle
    ):
        results = await skill_event_repo.get_for_config_bundle(sample_config_bundle.id)

        assert len(results) > 0
        assert results[0].skill is not None

    async def test_get_for_config_bundle_empty_for_unknown(self, skill_event_repo):
        results = await skill_event_repo.get_for_config_bundle(999999)

        assert results == []