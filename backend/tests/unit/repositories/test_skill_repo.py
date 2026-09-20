import pytest

from src.repositories.skill_repo import SkillRepository

pytestmark = pytest.mark.db


@pytest.fixture
def skill_repo(db_session):
    return SkillRepository(db_session)


class TestSkillRepository:

    async def test_get_by_name_found(self, skill_repo, sample_skill):
        found = await skill_repo.get_by_name(sample_skill.skill_name)

        assert found is not None
        assert found.id == sample_skill.id

    async def test_get_by_name_not_found(self, skill_repo):
        found = await skill_repo.get_by_name("nonexistent-skill")

        assert found is None

    async def test_record_selection_increments_freq(
        self, skill_repo, sample_skill, sample_user
    ):
        initial_freq = sample_skill.skill_selected_freq

        await skill_repo.record_selection(sample_skill.id, sample_user.id)

        assert sample_skill.skill_selected_freq == initial_freq + 1

    async def test_record_selection_returns_skill(
        self, skill_repo, sample_skill, sample_user
    ):
        result = await skill_repo.record_selection(sample_skill.id, sample_user.id)

        assert result is not None
        assert result.id == sample_skill.id

    async def test_record_selection_with_config_bundle(
        self, skill_repo, sample_skill, sample_user, sample_config_bundle
    ):
        result = await skill_repo.record_selection(
            sample_skill.id, sample_user.id, config_bundle_id=sample_config_bundle.id
        )

        assert result is not None

    async def test_record_selection_unknown_skill_raises(
        self, skill_repo, sample_user
    ):
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await skill_repo.record_selection(999999, sample_user.id)

    async def test_add_domain_appends_once(
        self, skill_repo, sample_skill, sample_knowledge_domain
    ):
        await skill_repo.add_domain(sample_skill, sample_knowledge_domain)
        await skill_repo.add_domain(sample_skill, sample_knowledge_domain)

        assert len(sample_skill.domains) == 1
        assert sample_knowledge_domain in sample_skill.domains

    async def test_add_domain_allows_multiple_domains(
        self, skill_repo, sample_skill, sample_knowledge_domain, another_knowledge_domain
    ):
        await skill_repo.add_domain(sample_skill, sample_knowledge_domain)
        await skill_repo.add_domain(sample_skill, another_knowledge_domain)

        assert {d.id for d in sample_skill.domains} == {
            sample_knowledge_domain.id,
            another_knowledge_domain.id,
        }

    async def test_list_by_domain_returns_skills(
        self, skill_repo, skill_with_domain, sample_knowledge_domain
    ):
        results = await skill_repo.list_by_domain(sample_knowledge_domain.id)

        ids = {s.id for s in results}
        assert skill_with_domain.id in ids

    async def test_list_by_domain_empty_for_unknown(self, skill_repo):
        results = await skill_repo.list_by_domain(999999)

        assert results == []

    async def test_list_by_domain_excludes_other_domains(
        self, skill_repo, skill_with_domain, another_knowledge_domain
    ):
        results = await skill_repo.list_by_domain(another_knowledge_domain.id)

        ids = {s.id for s in results}
        assert skill_with_domain.id not in ids