from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.enums.skill_visibility import SkillVisibility
from src.services import user_skill_service as mod
from src.services.errors import ConflictError, NotFoundError
from src.services.user_skill_service import (
    MAX_DESCRIPTION_LENGTH,
    MAX_NAME_LENGTH,
    UserSkillService,
)

ACTOR = SimpleNamespace(id=5)
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_skill(id=1, name="s", archived=False):
    return SimpleNamespace(
        id=id, skill_name=name, description="d", content="c", archived_at=NOW if archived else None
    )


@pytest.fixture(autouse=True)
def fake_markdown(monkeypatch):
    monkeypatch.setattr(mod, "clean_skill_body", lambda c: c.strip())
    monkeypatch.setattr(mod, "render_skill_md", lambda n, d, c: f"md:{n}:{d}:{c}")


@pytest.fixture
def skill_repo():
    repo = AsyncMock()
    repo.get_owned_by_name.return_value = None
    repo.count_owned_active.return_value = 0
    return repo


@pytest.fixture
def domain_repo():
    return AsyncMock()


@pytest.fixture
def service(skill_repo, domain_repo):
    return UserSkillService(skill_repo, domain_repo, max_private_skills=2)


class TestListAndGet:
    async def test_list_delegates(self, service, skill_repo):
        await service.list_skills(ACTOR, limit=5, offset=2, include_archived=True)

        skill_repo.list_owned.assert_awaited_once_with(5, limit=5, offset=2, include_archived=True)

    async def test_get_returns_owned_skill(self, service, skill_repo):
        skill = make_skill()
        skill_repo.get_owned_by_id.return_value = skill

        assert await service.get_skill(ACTOR, 1) is skill
        skill_repo.get_owned_by_id.assert_awaited_once_with(1, 5)

    async def test_get_not_found(self, service, skill_repo):
        skill_repo.get_owned_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Skill not found"):
            await service.get_skill(ACTOR, 1)


class TestCreateSkill:
    async def test_creates_private_skill(self, service, skill_repo, domain_repo):
        created = make_skill(id=9)
        skill_repo.create.return_value = created
        skill_repo.get_owned_by_id.return_value = created
        domain = SimpleNamespace(id=1)
        domain_repo.get_by_id.return_value = domain

        result = await service.create_skill(ACTOR, " name ", "  a   b \n c ", "  body ", [1, 1])

        assert result is created
        skill_repo.create.assert_awaited_once_with(
            skill_name="name", description="a b c", content="body",
            visibility=SkillVisibility.PRIVATE, owner_id=5,
        )
        domain_repo.get_by_id.assert_awaited_once_with(1)
        skill_repo.add_domain.assert_awaited_once_with(created, domain)

    @pytest.mark.parametrize("name", ["", "   ", None])
    async def test_rejects_empty_name(self, service, name):
        with pytest.raises(ValueError, match="Skill name must not be empty"):
            await service.create_skill(ACTOR, name, "d", "c")

    async def test_rejects_too_long_name(self, service):
        with pytest.raises(ValueError, match="must not exceed"):
            await service.create_skill(ACTOR, "n" * (MAX_NAME_LENGTH + 1), "d", "c")

    async def test_accepts_max_length_name(self, service, skill_repo):
        skill_repo.create.return_value = make_skill()
        skill_repo.get_owned_by_id.return_value = make_skill()

        await service.create_skill(ACTOR, "n" * MAX_NAME_LENGTH, "d", "c")

    @pytest.mark.parametrize("description", ["", "  \n ", None])
    async def test_rejects_empty_description(self, service, description):
        with pytest.raises(ValueError, match="description must not be empty"):
            await service.create_skill(ACTOR, "n", description, "c")

    async def test_rejects_too_long_description(self, service):
        with pytest.raises(ValueError, match="description must not exceed"):
            await service.create_skill(ACTOR, "n", "d" * (MAX_DESCRIPTION_LENGTH + 1), "c")

    async def test_rejects_duplicate_name(self, service, skill_repo):
        skill_repo.get_owned_by_name.return_value = make_skill()

        with pytest.raises(ConflictError, match="already have a skill named 'n'"):
            await service.create_skill(ACTOR, "n", "d", "c")

        skill_repo.create.assert_not_awaited()

    async def test_rejects_when_quota_reached(self, service, skill_repo):
        skill_repo.count_owned_active.return_value = 2

        with pytest.raises(ConflictError, match="at most 2 active private skills"):
            await service.create_skill(ACTOR, "n", "d", "c")

        skill_repo.create.assert_not_awaited()

    async def test_missing_domain_prevents_creation(self, service, skill_repo, domain_repo):
        domain_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Domain 1 not found"):
            await service.create_skill(ACTOR, "n", "d", "c", [1])

        skill_repo.create.assert_not_awaited()


class TestImportMarkdown:
    async def test_uses_frontmatter(self, service, monkeypatch):
        monkeypatch.setattr(mod, "split_frontmatter", lambda md: ({"name": "fm", "description": "fd"}, "body"))
        service.create_skill = AsyncMock()

        await service.import_markdown(ACTOR, "---\n---\nbody")

        service.create_skill.assert_awaited_once_with(ACTOR, "fm", "fd", "body", None)

    async def test_explicit_arguments_win(self, service, monkeypatch):
        monkeypatch.setattr(mod, "split_frontmatter", lambda md: ({"name": "fm", "description": "fd"}, "body"))
        service.create_skill = AsyncMock()

        await service.import_markdown(ACTOR, "x", skill_name="own", description="od", domain_ids=[1])

        service.create_skill.assert_awaited_once_with(ACTOR, "own", "od", "body", [1])

    @pytest.mark.parametrize("meta", [{}, {"name": "n"}, {"description": "d"}, {"name": " ", "description": "d"}])
    async def test_requires_name_and_description(self, service, monkeypatch, meta):
        monkeypatch.setattr(mod, "split_frontmatter", lambda md: (meta, "body"))

        with pytest.raises(ValueError, match="name and description are required"):
            await service.import_markdown(ACTOR, "x")

    async def test_none_markdown_is_treated_as_empty(self, service, monkeypatch):
        seen = []
        monkeypatch.setattr(mod, "split_frontmatter", lambda md: (seen.append(md) or {}, ""))

        with pytest.raises(ValueError):
            await service.import_markdown(ACTOR, None)

        assert seen == [""]


class TestUpdateSkill:
    @pytest.fixture
    def skill(self, skill_repo):
        s = make_skill(name="old")
        skill_repo.get_owned_by_id.return_value = s
        return s

    async def test_updates_all_fields(self, service, skill_repo, skill):
        await service.update_skill(ACTOR, 1, skill_name=" new ", description=" a  b ", content=" body ")

        skill_repo.update.assert_awaited_once_with(
            skill, skill_name="new", description="a b", content="body"
        )

    async def test_same_name_skips_uniqueness_check(self, service, skill_repo, skill):
        await service.update_skill(ACTOR, 1, skill_name="old")

        skill_repo.get_owned_by_name.assert_not_awaited()
        skill_repo.update.assert_not_awaited()

    async def test_rename_conflict(self, service, skill_repo, skill):
        skill_repo.get_owned_by_name.return_value = make_skill(id=2)

        with pytest.raises(ConflictError):
            await service.update_skill(ACTOR, 1, skill_name="taken")

        skill_repo.update.assert_not_awaited()

    async def test_rename_to_itself_via_lookup_is_allowed(self, service, skill_repo, skill):
        skill_repo.get_owned_by_name.return_value = skill

        await service.update_skill(ACTOR, 1, skill_name="renamed")

        skill_repo.update.assert_awaited_once_with(skill, skill_name="renamed")

    async def test_nothing_to_update(self, service, skill_repo, skill):
        await service.update_skill(ACTOR, 1)

        skill_repo.update.assert_not_awaited()

    async def test_not_found(self, service, skill_repo):
        skill_repo.get_owned_by_id.return_value = None

        with pytest.raises(NotFoundError):
            await service.update_skill(ACTOR, 1, description="d")


class TestArchiveRestore:
    async def test_archive(self, service, skill_repo):
        skill = make_skill()
        skill_repo.get_owned_by_id.return_value = skill

        await service.archive_skill(ACTOR, 1)

        skill_repo.archive.assert_awaited_once_with(skill)

    async def test_restore_archived_checks_quota(self, service, skill_repo):
        skill = make_skill(archived=True)
        skill_repo.get_owned_by_id.return_value = skill

        await service.restore_skill(ACTOR, 1)

        skill_repo.restore.assert_awaited_once_with(skill)

    async def test_restore_blocked_by_quota(self, service, skill_repo):
        skill_repo.get_owned_by_id.return_value = make_skill(archived=True)
        skill_repo.count_owned_active.return_value = 2

        with pytest.raises(ConflictError):
            await service.restore_skill(ACTOR, 1)

        skill_repo.restore.assert_not_awaited()

    async def test_restore_active_skill_is_noop(self, service, skill_repo):
        skill_repo.get_owned_by_id.return_value = make_skill()
        skill_repo.count_owned_active.return_value = 2

        await service.restore_skill(ACTOR, 1)

        skill_repo.restore.assert_not_awaited()


class TestExportMarkdown:
    async def test_renders(self, service, skill_repo):
        skill_repo.get_owned_by_id.return_value = SimpleNamespace(skill_name="n", description="d", content="c")

        assert await service.export_markdown(ACTOR, 1) == "md:n:d:c"