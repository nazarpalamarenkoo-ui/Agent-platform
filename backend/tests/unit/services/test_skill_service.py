from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.enums.notification_type import NotificationType
from src.db.enums.skill_visibility import SkillVisibility
from src.services import skill_service as mod
from src.services.errors import ConflictError, ForbiddenError, NotFoundError
from src.services.skill_service import MAX_CONTENT_CHARS, SkillService

ADMIN = SimpleNamespace(id=1, is_admin=True)
USER = SimpleNamespace(id=2, is_admin=False)
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_skill(id=1, visibility=SkillVisibility.GLOBAL, archived=False, **kw):
    return SimpleNamespace(
        id=id, visibility=visibility, archived_at=NOW if archived else None,
        skill_name="s", description="d", content="c", **kw,
    )


@pytest.fixture(autouse=True)
def fake_markdown(monkeypatch):
    clean = MagicMock(side_effect=lambda content, limit=None: content.strip())
    monkeypatch.setattr(mod, "clean_skill_body", clean)
    monkeypatch.setattr(mod, "render_skill_md", lambda n, d, c: f"md:{n}:{d}:{c}")
    return clean


@pytest.fixture
def skill_repo():
    repo = AsyncMock()
    repo.get_global_by_name.return_value = None
    return repo


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def bundle_repo():
    return AsyncMock()


@pytest.fixture
def notification_repo():
    return AsyncMock()


@pytest.fixture
def service(skill_repo, domain_repo, bundle_repo, notification_repo):
    return SkillService(skill_repo, domain_repo, bundle_repo, notification_repo)


class TestListSkills:
    async def test_lists_visible_for_regular_listing(self, service, skill_repo):
        await service.list_skills(USER, limit=5, offset=1, domain_id=3)

        skill_repo.list_visible.assert_awaited_once_with(2, limit=5, offset=1, domain_id=3)

    async def test_include_archived_requires_admin(self, service, skill_repo):
        with pytest.raises(ForbiddenError):
            await service.list_skills(USER, include_archived=True)

        skill_repo.admin_list_global.assert_not_awaited()

    async def test_admin_includes_archived(self, service, skill_repo):
        await service.list_skills(ADMIN, include_archived=True)

        skill_repo.admin_list_global.assert_awaited_once_with(limit=100, offset=0, include_archived=True)


class TestGetSkill:
    async def test_returns_visible_skill(self, service, skill_repo):
        skill = make_skill()
        skill_repo.get_visible.return_value = skill

        assert await service.get_skill(USER, 1) is skill
        skill_repo.get_visible.assert_awaited_once_with(1, 2)

    async def test_admin_can_see_archived_global_skill(self, service, skill_repo):
        skill = make_skill(archived=True)
        skill_repo.get_visible.return_value = None
        skill_repo.admin_get_by_id.return_value = skill

        assert await service.get_skill(ADMIN, 1) is skill

    async def test_admin_cannot_see_foreign_private_skill(self, service, skill_repo):
        skill_repo.get_visible.return_value = None
        skill_repo.admin_get_by_id.return_value = make_skill(visibility=SkillVisibility.PRIVATE)

        with pytest.raises(NotFoundError, match="Skill not found"):
            await service.get_skill(ADMIN, 1)

    async def test_regular_user_gets_not_found(self, service, skill_repo):
        skill_repo.get_visible.return_value = None

        with pytest.raises(NotFoundError):
            await service.get_skill(USER, 1)

        skill_repo.admin_get_by_id.assert_not_awaited()

    async def test_admin_not_found(self, service, skill_repo):
        skill_repo.get_visible.return_value = None
        skill_repo.admin_get_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.get_skill(ADMIN, 1)


class TestExportSkillMd:
    async def test_renders_markdown(self, service, skill_repo):
        skill_repo.get_visible.return_value = SimpleNamespace(skill_name="n", description="d", content="c")

        assert await service.export_skill_md(USER, 1) == "md:n:d:c"


class TestCreateGlobalSkill:
    async def test_requires_admin(self, service, skill_repo):
        with pytest.raises(ForbiddenError):
            await service.create_global_skill(USER, "n", "d", "c")

        skill_repo.create.assert_not_awaited()

    @pytest.mark.parametrize("name", ["", "  ", None])
    async def test_rejects_empty_name(self, service, name):
        with pytest.raises(ValueError, match="Skill name must not be empty"):
            await service.create_global_skill(ADMIN, name, "d", "c")

    async def test_rejects_duplicate_name(self, service, skill_repo):
        skill_repo.get_global_by_name.return_value = make_skill()

        with pytest.raises(ConflictError, match="Skill 'n' already exists"):
            await service.create_global_skill(ADMIN, " n ", "d", "c")

        skill_repo.get_global_by_name.assert_awaited_once_with("n")
        skill_repo.create.assert_not_awaited()

    async def test_creates_global_skill_with_domains(
        self, service, skill_repo, domain_repo, fake_markdown
    ):
        created = make_skill(id=9)
        skill_repo.create.return_value = created
        skill_repo.admin_get_by_id.return_value = created
        d1, d2 = SimpleNamespace(id=1), SimpleNamespace(id=2)
        domain_repo.get_by_id.side_effect = [d1, d2]

        result = await service.create_global_skill(ADMIN, " n ", "desc", "  body  ", [1, 2, 1])

        assert result is created
        fake_markdown.assert_called_once_with("  body  ", MAX_CONTENT_CHARS)
        skill_repo.create.assert_awaited_once_with(
            skill_name="n", description="desc", content="body",
            visibility=SkillVisibility.GLOBAL, owner_id=None,
        )
        assert domain_repo.get_by_id.await_count == 2
        assert [c.args[1] for c in skill_repo.add_domain.await_args_list] == [d1, d2]

    async def test_missing_domain_prevents_creation(self, service, skill_repo, domain_repo):
        domain_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Domain 1 not found"):
            await service.create_global_skill(ADMIN, "n", "d", "c", [1])

        skill_repo.create.assert_not_awaited()


class TestUpdateGlobalSkill:
    async def test_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.update_global_skill(USER, 1, description="x")

    async def test_rejects_private_skill(self, service, skill_repo):
        skill_repo.admin_get_by_id.return_value = make_skill(visibility=SkillVisibility.PRIVATE)

        with pytest.raises(NotFoundError):
            await service.update_global_skill(ADMIN, 1, description="x")

    async def test_updates_description_and_cleans_content(self, service, skill_repo):
        skill = make_skill()
        skill_repo.admin_get_by_id.return_value = skill

        await service.update_global_skill(ADMIN, 1, description="new", content="  body ")

        skill_repo.update.assert_awaited_once_with(skill, description="new", content="body")

    async def test_no_changes_no_update(self, service, skill_repo):
        skill_repo.admin_get_by_id.return_value = make_skill()

        await service.update_global_skill(ADMIN, 1)

        skill_repo.update.assert_not_awaited()


class TestArchiveSkill:
    async def test_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.archive_skill(USER, 1)

    async def test_archives_and_notifies_affected_users(
        self, service, skill_repo, bundle_repo, notification_repo
    ):
        skill = make_skill()
        skill_repo.admin_get_by_id.return_value = skill
        bundle_repo.list_user_ids_with_skill.return_value = [5, 6]

        await service.archive_skill(ADMIN, 1)

        skill_repo.archive.assert_awaited_once_with(skill)
        bundle_repo.list_user_ids_with_skill.assert_awaited_once_with(1)
        notification_repo.create_missing.assert_awaited_once_with(
            [5, 6], NotificationType.SKILL_ARCHIVED, skill_id=1
        )

    async def test_already_archived_is_idempotent(
        self, service, skill_repo, bundle_repo, notification_repo
    ):
        skill_repo.admin_get_by_id.return_value = make_skill(archived=True)

        await service.archive_skill(ADMIN, 1)

        skill_repo.archive.assert_not_awaited()
        notification_repo.create_missing.assert_not_awaited()

    async def test_private_skill_cannot_be_archived_here(self, service, skill_repo):
        skill_repo.admin_get_by_id.return_value = make_skill(visibility=SkillVisibility.PRIVATE)

        with pytest.raises(NotFoundError):
            await service.archive_skill(ADMIN, 1)


class TestRestoreSkill:
    async def test_requires_admin(self, service):
        with pytest.raises(ForbiddenError):
            await service.restore_skill(USER, 1)

    async def test_restores_and_clears_notifications(self, service, skill_repo, notification_repo):
        skill = make_skill(archived=True)
        skill_repo.admin_get_by_id.return_value = skill

        await service.restore_skill(ADMIN, 1)

        skill_repo.restore.assert_awaited_once_with(skill)
        notification_repo.delete_for_item.assert_awaited_once_with(
            NotificationType.SKILL_ARCHIVED, skill_id=1
        )

    async def test_active_skill_is_noop(self, service, skill_repo, notification_repo):
        skill_repo.admin_get_by_id.return_value = make_skill()

        await service.restore_skill(ADMIN, 1)

        skill_repo.restore.assert_not_awaited()
        notification_repo.delete_for_item.assert_not_awaited()