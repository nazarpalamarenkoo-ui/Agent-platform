import pytest
import pytest_asyncio

from src.db.enums.notification_type import NotificationType
from src.db.enums.skill_visibility import SkillVisibility
from src.db.enums.user_role import UserRole
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_domain_repo import KnowledgeDomainRepository
from src.repositories.notification_repo import NotificationRepository
from src.repositories.skill_repo import SkillRepository
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.skill_service import SkillService


@pytest.fixture
def service(db_session):
    return SkillService(
        SkillRepository(db_session),
        KnowledgeDomainRepository(db_session),
        ConfigBundleRepository(db_session),
        NotificationRepository(db_session),
    )


@pytest_asyncio.fixture
async def admin(make_user):
    return await make_user(role=UserRole.ADMIN)


class TestCreateGlobalSkill:
    async def test_persists_global_skill_with_domain_links(
        self, service, admin, sample_knowledge_domain, another_knowledge_domain
    ):
        skill = await service.create_global_skill(
            admin,
            "  research  ",
            "Looks things up",
            "# Body\ntext",
            domain_ids=[
                sample_knowledge_domain.id,
                another_knowledge_domain.id,
                sample_knowledge_domain.id,
            ],
        )

        assert skill.id is not None
        assert skill.skill_name == "research"
        assert skill.visibility == SkillVisibility.GLOBAL
        assert skill.owner_id is None
        assert {d.id for d in skill.domains} == {
            sample_knowledge_domain.id,
            another_knowledge_domain.id,
        }

    async def test_forbidden_for_regular_user(self, service, sample_user):
        with pytest.raises(ForbiddenError, match="Admin access required"):
            await service.create_global_skill(sample_user, "s", "d", "c")

    async def test_raises_for_empty_name(self, service, admin):
        with pytest.raises(ValueError, match="Skill name must not be empty"):
            await service.create_global_skill(admin, "   ", "d", "c")

    async def test_raises_on_duplicate_global_name(self, service, admin):
        await service.create_global_skill(admin, "dup", "d", "c")

        with pytest.raises(ConflictError, match="Skill 'dup' already exists"):
            await service.create_global_skill(admin, "dup", "d2", "c2")

    async def test_raises_when_domain_missing_and_creates_nothing(
        self, service, admin, db_session
    ):
        with pytest.raises(NotFoundError, match="Domain 999999 not found"):
            await service.create_global_skill(
                admin, "orphan", "d", "c", domain_ids=[999_999]
            )

        assert await SkillRepository(db_session).get_global_by_name("orphan") is None


class TestUpdateGlobalSkill:
    async def test_updates_description_and_content(self, service, admin):
        skill = await service.create_global_skill(admin, "upd", "old", "old body")

        updated = await service.update_global_skill(
            admin, skill.id, description="new", content="new body"
        )

        assert updated.description == "new"
        assert "new body" in updated.content

    async def test_keeps_fields_when_none_passed(self, service, admin):
        skill = await service.create_global_skill(admin, "keep", "desc", "body")

        updated = await service.update_global_skill(admin, skill.id)

        assert updated.description == "desc"

    async def test_forbidden_for_regular_user(self, service, sample_user, make_skill):
        skill = await make_skill()
        with pytest.raises(ForbiddenError):
            await service.update_global_skill(sample_user, skill.id, description="x")

    async def test_raises_for_private_skill(self, service, admin, sample_user, make_skill):
        private = await make_skill(owner=sample_user)
        with pytest.raises(NotFoundError, match="Skill not found"):
            await service.update_global_skill(admin, private.id, description="x")

    async def test_raises_for_unknown_skill(self, service, admin):
        with pytest.raises(NotFoundError):
            await service.update_global_skill(admin, 999_999, description="x")


class TestArchiveAndRestore:
    async def test_archive_marks_skill_and_notifies_bundle_owners(
        self,
        service,
        admin,
        db_session,
        sample_user,
        another_user,
        sample_agent_profile,
        make_bundle,
        make_skill,
    ):
        skill = await make_skill()
        bundle_repo = ConfigBundleRepository(db_session)
        bundle = await make_bundle(sample_user, sample_agent_profile)
        await bundle_repo.add_skill(bundle, skill)

        archived = await service.archive_skill(admin, skill.id)

        assert archived.archived_at is not None
        notifications = NotificationRepository(db_session)
        assert await notifications.count_unread(sample_user.id) == 1
        assert await notifications.count_unread(another_user.id) == 0

    async def test_archive_is_idempotent_and_does_not_duplicate_notifications(
        self, service, admin, db_session, sample_user, sample_agent_profile,
        make_bundle, make_skill,
    ):
        skill = await make_skill()
        bundle = await make_bundle(sample_user, sample_agent_profile)
        await ConfigBundleRepository(db_session).add_skill(bundle, skill)

        await service.archive_skill(admin, skill.id)
        await service.archive_skill(admin, skill.id)

        assert await NotificationRepository(db_session).count_unread(sample_user.id) == 1

    async def test_restore_clears_archived_and_removes_notifications(
        self, service, admin, db_session, sample_user, sample_agent_profile,
        make_bundle, make_skill,
    ):
        skill = await make_skill()
        bundle = await make_bundle(sample_user, sample_agent_profile)
        await ConfigBundleRepository(db_session).add_skill(bundle, skill)
        await service.archive_skill(admin, skill.id)

        restored = await service.restore_skill(admin, skill.id)

        assert restored.archived_at is None
        assert await NotificationRepository(db_session).count_unread(sample_user.id) == 0

    async def test_restore_of_active_skill_is_noop(self, service, admin, make_skill):
        skill = await make_skill()

        restored = await service.restore_skill(admin, skill.id)

        assert restored.archived_at is None

    async def test_archive_forbidden_for_regular_user(
        self, service, sample_user, make_skill
    ):
        skill = await make_skill()
        with pytest.raises(ForbiddenError):
            await service.archive_skill(sample_user, skill.id)


class TestListSkills:
    async def test_user_sees_global_and_own_private_but_not_foreign_private(
        self, service, sample_user, another_user, make_skill
    ):
        global_skill = await make_skill()
        own = await make_skill(owner=sample_user)
        foreign = await make_skill(owner=another_user)

        ids = {s.id for s in await service.list_skills(sample_user)}

        assert global_skill.id in ids
        assert own.id in ids
        assert foreign.id not in ids

    async def test_filters_by_domain(
        self, service, admin, sample_knowledge_domain, another_knowledge_domain
    ):
        a = await service.create_global_skill(
            admin, "in-a", "d", "c", domain_ids=[sample_knowledge_domain.id]
        )
        b = await service.create_global_skill(
            admin, "in-b", "d", "c", domain_ids=[another_knowledge_domain.id]
        )

        ids = {
            s.id
            for s in await service.list_skills(
                admin, domain_id=sample_knowledge_domain.id
            )
        }

        assert a.id in ids
        assert b.id not in ids

    async def test_include_archived_requires_admin(self, service, sample_user):
        with pytest.raises(ForbiddenError):
            await service.list_skills(sample_user, include_archived=True)

    async def test_admin_include_archived_returns_archived_global_skills(
        self, service, admin, make_skill
    ):
        skill = await make_skill()
        await service.archive_skill(admin, skill.id)

        visible = {s.id for s in await service.list_skills(admin)}
        with_archived = {
            s.id for s in await service.list_skills(admin, include_archived=True)
        }

        assert skill.id not in visible
        assert skill.id in with_archived

    async def test_respects_limit_and_offset(self, service, sample_user, make_skill):
        for _ in range(3):
            await make_skill()

        first = await service.list_skills(sample_user, limit=1, offset=0)
        second = await service.list_skills(sample_user, limit=1, offset=1)

        assert len(first) == len(second) == 1
        assert first[0].id != second[0].id


class TestGetSkill:
    async def test_returns_visible_global_skill(self, service, sample_user, make_skill):
        skill = await make_skill()
        assert (await service.get_skill(sample_user, skill.id)).id == skill.id

    async def test_returns_own_private_skill(self, service, sample_user, make_skill):
        skill = await make_skill(owner=sample_user)
        assert (await service.get_skill(sample_user, skill.id)).id == skill.id

    async def test_hides_foreign_private_skill_even_from_admin(
        self, service, admin, another_user, make_skill
    ):
        foreign = await make_skill(owner=another_user)
        with pytest.raises(NotFoundError):
            await service.get_skill(admin, foreign.id)

    async def test_admin_can_read_archived_global_skill(
        self, service, admin, make_skill
    ):
        skill = await make_skill()
        await service.archive_skill(admin, skill.id)

        assert (await service.get_skill(admin, skill.id)).id == skill.id

    async def test_raises_for_unknown_id(self, service, sample_user):
        with pytest.raises(NotFoundError, match="Skill not found"):
            await service.get_skill(sample_user, 999_999)


class TestExportSkillMd:
    async def test_renders_name_description_and_content(
        self, service, sample_user, make_skill
    ):
        skill = await make_skill(
            skill_name="exported", description="Exported desc", content="Body text"
        )

        md = await service.export_skill_md(sample_user, skill.id)

        assert "exported" in md
        assert "Exported desc" in md
        assert "Body text" in md

    async def test_raises_for_invisible_skill(
        self, service, sample_user, another_user, make_skill
    ):
        foreign = await make_skill(owner=another_user)
        with pytest.raises(NotFoundError):
            await service.export_skill_md(sample_user, foreign.id)