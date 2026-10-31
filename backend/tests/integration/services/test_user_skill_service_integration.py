import pytest

from src.db.enums.skill_visibility import SkillVisibility
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.skill_repo import SkillRepository
from src.services.errors import ConflictError, NotFoundError
from src.services.user_skill_service import (
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
    UserSkillService,
)


@pytest.fixture
def service(db_session):
    return UserSkillService(
        SkillRepository(db_session),
        KnowledgeDomainRepository(db_session),
        max_private_skills=3,
    )


class TestCreateSkill:
    async def test_persists_private_skill_owned_by_actor(
        self, service, sample_user, sample_knowledge_domain
    ):
        skill = await service.create_skill(
            sample_user,
            "  my-skill ",
            "  multi   word \n description ",
            "# Body",
            [sample_knowledge_domain.id, sample_knowledge_domain.id],
        )

        assert skill.skill_name == "my-skill"
        assert skill.description == "multi word description"
        assert skill.visibility == SkillVisibility.PRIVATE
        assert skill.owner_id == sample_user.id
        assert [d.id for d in skill.domains] == [sample_knowledge_domain.id]

    async def test_raises_for_empty_name(self, service, sample_user):
        with pytest.raises(ValueError, match="name must not be empty"):
            await service.create_skill(sample_user, " ", "d", "c")

    async def test_raises_for_too_long_name(self, service, sample_user):
        with pytest.raises(ValueError, match=str(MAX_NAME_LENGTH)):
            await service.create_skill(sample_user, "x" * (MAX_NAME_LENGTH + 1), "d", "c")

    async def test_raises_for_empty_description(self, service, sample_user):
        with pytest.raises(ValueError, match="description must not be empty"):
            await service.create_skill(sample_user, "n", "  ", "c")

    async def test_raises_for_too_long_description(self, service, sample_user):
        with pytest.raises(ValueError, match=str(MAX_DESCRIPTION_LENGTH)):
            await service.create_skill(
                sample_user, "n", "d" * (MAX_DESCRIPTION_LENGTH + 1), "c"
            )

    async def test_raises_on_duplicate_name_for_same_owner(self, service, sample_user):
        await service.create_skill(sample_user, "dup", "d", "c")

        with pytest.raises(ConflictError, match="already have a skill named 'dup'"):
            await service.create_skill(sample_user, "dup", "d", "c")

    async def test_same_name_allowed_for_different_owners(
        self, service, sample_user, another_user
    ):
        await service.create_skill(sample_user, "shared-name", "d", "c")
        other = await service.create_skill(another_user, "shared-name", "d", "c")

        assert other.owner_id == another_user.id

    async def test_enforces_quota(self, service, sample_user):
        for i in range(3):
            await service.create_skill(sample_user, f"s{i}", "d", "c")

        with pytest.raises(ConflictError, match="at most 3 active private skills"):
            await service.create_skill(sample_user, "s-extra", "d", "c")

    async def test_raises_for_missing_domain(self, service, sample_user):
        with pytest.raises(NotFoundError, match="Domain 999999 not found"):
            await service.create_skill(sample_user, "n", "d", "c", [999_999])


class TestImportMarkdown:
    MD = "---\nname: imported\ndescription: From frontmatter\n---\n# Heading\nBody"

    async def test_reads_name_and_description_from_frontmatter(self, service, sample_user):
        skill = await service.import_markdown(sample_user, self.MD)

        assert skill.skill_name == "imported"
        assert skill.description == "From frontmatter"
        assert "Body" in skill.content

    async def test_explicit_arguments_override_frontmatter(self, service, sample_user):
        skill = await service.import_markdown(
            sample_user, self.MD, skill_name="explicit", description="Explicit desc"
        )

        assert skill.skill_name == "explicit"
        assert skill.description == "Explicit desc"

    async def test_raises_when_name_or_description_missing(self, service, sample_user):
        with pytest.raises(ValueError, match="name and description are required"):
            await service.import_markdown(sample_user, "just body")


class TestUpdateSkill:
    async def test_updates_all_fields(self, service, sample_user):
        skill = await service.create_skill(sample_user, "old", "old d", "old c")

        updated = await service.update_skill(
            sample_user, skill.id, skill_name="new", description="new d", content="new c"
        )

        assert updated.skill_name == "new"
        assert updated.description == "new d"
        assert "new c" in updated.content

    async def test_raises_on_rename_conflict(self, service, sample_user):
        await service.create_skill(sample_user, "taken", "d", "c")
        other = await service.create_skill(sample_user, "other", "d", "c")

        with pytest.raises(ConflictError):
            await service.update_skill(sample_user, other.id, skill_name="taken")

    async def test_renaming_to_same_name_is_allowed(self, service, sample_user):
        skill = await service.create_skill(sample_user, "same", "d", "c")

        updated = await service.update_skill(sample_user, skill.id, skill_name="same")

        assert updated.skill_name == "same"

    async def test_cannot_update_foreign_skill(self, service, sample_user, another_user):
        skill = await service.create_skill(another_user, "theirs", "d", "c")

        with pytest.raises(NotFoundError):
            await service.update_skill(sample_user, skill.id, description="x")


class TestArchiveAndRestore:
    async def test_archive_frees_quota_and_restore_consumes_it(self, service, sample_user):
        skills = [
            await service.create_skill(sample_user, f"s{i}", "d", "c") for i in range(3)
        ]

        archived = await service.archive_skill(sample_user, skills[0].id)
        assert archived.archived_at is not None

        await service.create_skill(sample_user, "replacement", "d", "c")

        with pytest.raises(ConflictError, match="at most 3"):
            await service.restore_skill(sample_user, skills[0].id)

    async def test_restore_clears_archived_at(self, service, sample_user):
        skill = await service.create_skill(sample_user, "r", "d", "c")
        await service.archive_skill(sample_user, skill.id)

        restored = await service.restore_skill(sample_user, skill.id)

        assert restored.archived_at is None

    async def test_restore_of_active_skill_is_noop_even_at_quota(
        self, service, sample_user
    ):
        skills = [
            await service.create_skill(sample_user, f"s{i}", "d", "c") for i in range(3)
        ]

        restored = await service.restore_skill(sample_user, skills[0].id)

        assert restored.archived_at is None


class TestListAndGet:
    async def test_lists_only_own_skills(self, service, sample_user, another_user):
        mine = await service.create_skill(sample_user, "mine", "d", "c")
        theirs = await service.create_skill(another_user, "theirs", "d", "c")

        ids = {s.id for s in await service.list_skills(sample_user)}

        assert mine.id in ids
        assert theirs.id not in ids

    async def test_archived_hidden_unless_requested(self, service, sample_user):
        skill = await service.create_skill(sample_user, "arch", "d", "c")
        await service.archive_skill(sample_user, skill.id)

        default = {s.id for s in await service.list_skills(sample_user)}
        with_archived = {
            s.id for s in await service.list_skills(sample_user, include_archived=True)
        }

        assert skill.id not in default
        assert skill.id in with_archived

    async def test_get_skill_raises_for_foreign_skill(
        self, service, sample_user, another_user
    ):
        skill = await service.create_skill(another_user, "theirs", "d", "c")
        with pytest.raises(NotFoundError, match="Skill not found"):
            await service.get_skill(sample_user, skill.id)

    async def test_export_markdown_round_trips_through_import(self, service, sample_user):
        skill = await service.create_skill(sample_user, "round-trip", "Round desc", "Body text")

        md = await service.export_markdown(sample_user, skill.id)
        imported = await service.import_markdown(
            sample_user, md, skill_name="round-trip-copy"
        )

        assert imported.description == "Round desc"
        assert "Body text" in imported.content