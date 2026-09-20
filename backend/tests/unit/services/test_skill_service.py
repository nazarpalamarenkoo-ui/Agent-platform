from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.skill_service import SkillService


@pytest.fixture
def skill_repo():
    return AsyncMock()


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def service(skill_repo, domain_repo):
    return SkillService(skill_repo, domain_repo)


class TestCreateSkill:
    async def test_creates_skill_with_domains(
        self, service, skill_repo, domain_repo
    ):
        skill_repo.get_by_name.return_value = None
        skill = MagicMock()
        skill_repo.create.return_value = skill
        domain_repo.get_by_id.return_value = MagicMock()

        result = await service.create_skill(
            skill_name="summarization", description="desc", domain_ids=[1, 2]
        )

        assert result is skill
        skill_repo.create.assert_awaited_once_with(
            skill_name="summarization", description="desc"
        )
        assert domain_repo.get_by_id.await_count == 2
        assert skill_repo.add_domain.await_count == 2

    async def test_creates_skill_with_no_domains(
        self, service, skill_repo, domain_repo
    ):
        skill_repo.get_by_name.return_value = None
        skill = MagicMock()
        skill_repo.create.return_value = skill

        result = await service.create_skill(
            skill_name="summarization", description="desc", domain_ids=[]
        )

        assert result is skill
        domain_repo.get_by_id.assert_not_awaited()

    async def test_raises_when_skill_name_taken(self, service, skill_repo):
        skill_repo.get_by_name.return_value = MagicMock()

        with pytest.raises(
            ValueError, match="Skill 'summarization' already exists"
        ):
            await service.create_skill(
                skill_name="summarization", description="desc", domain_ids=[]
            )

        skill_repo.create.assert_not_awaited()

    async def test_raises_when_domain_not_found(
        self, service, skill_repo, domain_repo
    ):
        skill_repo.get_by_name.return_value = None
        skill_repo.create.return_value = MagicMock()
        domain_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Domain 1 not found"):
            await service.create_skill(
                skill_name="summarization", description="desc", domain_ids=[1]
            )


class TestGetSkillsByDomain:
    async def test_delegates_to_repo(self, service, skill_repo):
        skills = [MagicMock()]
        skill_repo.list_by_domain.return_value = skills

        result = await service.get_skills_by_domain(domain_id=1)

        assert result is skills
        skill_repo.list_by_domain.assert_awaited_once_with(1)


class TestGetSkill:
    async def test_returns_skill_when_found(self, service, skill_repo):
        skill = MagicMock()
        skill_repo.get_by_id.return_value = skill

        result = await service.get_skill(1)

        assert result is skill

    async def test_raises_when_not_found(self, service, skill_repo):
        skill_repo.get_by_id.return_value = None

        with pytest.raises(ValueError, match="Skill 1 not found"):
            await service.get_skill(1)


class TestGetAllSkills:
    async def test_returns_list_with_default_pagination(
        self, service, skill_repo
    ):
        skill_repo.get_all.return_value = (MagicMock(),)

        result = await service.get_all_skills()

        assert isinstance(result, list)
        assert len(result) == 1
        skill_repo.get_all.assert_awaited_once_with(limit=100, offset=0)

    async def test_returns_list_with_custom_pagination(
        self, service, skill_repo
    ):
        skill_repo.get_all.return_value = []

        await service.get_all_skills(limit=20, offset=40)

        skill_repo.get_all.assert_awaited_once_with(limit=20, offset=40)