import pytest

from src.services.skill_service import SkillService
from src.repositories.skill_repo import SkillRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository


@pytest.fixture
def service(db_session):
    return SkillService(
        SkillRepository(db_session),
        KnowledgeDomainRepository(db_session),
    )


class TestCreateSkill:
    async def test_persists_skill_with_real_domain_links(
        self, service, sample_knowledge_domain
    ):
        skill = await service.create_skill(
            skill_name="research",
            description="Looks things up",
            domain_ids=[sample_knowledge_domain.id],
        )

        assert skill.id is not None

        reloaded = await service.get_skill(skill.id)
        assert reloaded.skill_name == "research"
        assert [d.id for d in reloaded.domains] == [sample_knowledge_domain.id]

    async def test_raises_when_skill_name_already_exists(
        self, service, sample_knowledge_domain
    ):
        await service.create_skill(
            skill_name="dup-skill",
            description="d",
            domain_ids=[sample_knowledge_domain.id],
        )

        with pytest.raises(ValueError, match="Skill 'dup-skill' already exists"):
            await service.create_skill(
                skill_name="dup-skill",
                description="d2",
                domain_ids=[sample_knowledge_domain.id],
            )

    async def test_partially_links_domains_when_a_later_domain_id_is_invalid(
        self, service, sample_knowledge_domain
    ):
        with pytest.raises(ValueError, match="Domain 999999 not found"):
            await service.create_skill(
                skill_name="partial-skill",
                description="d",
                domain_ids=[sample_knowledge_domain.id, 999_999],
            )

        linked = await service.get_skills_by_domain(sample_knowledge_domain.id)
        assert "partial-skill" in [s.skill_name for s in linked]

    async def test_raises_when_first_domain_id_is_invalid(self, service):
        with pytest.raises(ValueError, match="Domain 999999 not found"):
            await service.create_skill(
                skill_name="orphan-skill", description="d", domain_ids=[999_999]
            )


class TestGetSkillsByDomain:
    async def test_returns_only_skills_linked_to_that_domain(
        self, service, sample_knowledge_domain, another_knowledge_domain
    ):
        await service.create_skill(
            skill_name="skill-a", description="d", domain_ids=[sample_knowledge_domain.id]
        )
        await service.create_skill(
            skill_name="skill-b", description="d", domain_ids=[another_knowledge_domain.id]
        )

        result = await service.get_skills_by_domain(sample_knowledge_domain.id)
        names = {s.skill_name for s in result}

        assert "skill-a" in names
        assert "skill-b" not in names


class TestGetSkill:
    async def test_returns_persisted_skill(self, service, sample_knowledge_domain):
        created = await service.create_skill(
            skill_name="lookup-skill", description="d", domain_ids=[sample_knowledge_domain.id]
        )

        result = await service.get_skill(created.id)
        assert result.id == created.id

    async def test_raises_for_unknown_id(self, service):
        with pytest.raises(ValueError, match="Skill 999999 not found"):
            await service.get_skill(999_999)


class TestGetAllSkills:
    async def test_returns_all_created_skills(self, service, sample_knowledge_domain):
        s1 = await service.create_skill(
            skill_name="all-skill-1", description="d", domain_ids=[sample_knowledge_domain.id]
        )
        s2 = await service.create_skill(
            skill_name="all-skill-2", description="d", domain_ids=[sample_knowledge_domain.id]
        )

        result = await service.get_all_skills()
        ids = {s.id for s in result}

        assert s1.id in ids
        assert s2.id in ids

    async def test_respects_limit_and_offset(self, service, sample_knowledge_domain):
        await service.create_skill(
            skill_name="page-skill-1", description="d", domain_ids=[sample_knowledge_domain.id]
        )
        await service.create_skill(
            skill_name="page-skill-2", description="d", domain_ids=[sample_knowledge_domain.id]
        )

        first_page = await service.get_all_skills(limit=1, offset=0)
        second_page = await service.get_all_skills(limit=1, offset=1)

        assert len(first_page) == 1
        assert len(second_page) == 1
        assert first_page[0].id != second_page[0].id