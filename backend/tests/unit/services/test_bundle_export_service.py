import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import bundle_export_service as mod
from src.services.bundle_export_service import (
    EXPORT_SCHEMA_VERSION,
    FIXED_ZIP_TIMESTAMP,
    BundleExportService,
)
from src.services.effective_bundle_service import (
    EffectiveBundle,
    EffectivePack,
    EffectiveSkill,
    EffectiveTool,
)
from src.services.errors import NotFoundError


@pytest.fixture(autouse=True)
def fake_markdown(monkeypatch):
    monkeypatch.setattr(mod, "assign_skill_dirs", lambda pairs: {i: f"{n}-{i}" for i, n in pairs})
    monkeypatch.setattr(
        mod, "render_skill_md", lambda name, desc, content: f"---\nname: {name}\n---\n{content}"
    )
    monkeypatch.setattr(mod, "skill_dir_name", lambda n: n.lower().replace(" ", "-"))


def make_skill(id, name, content="body", description="d", content_hash="h"):
    return SimpleNamespace(
        id=id, skill_name=name, description=description, content=content, content_hash=content_hash
    )


@pytest.fixture
def repos():
    bundle_repo = AsyncMock()
    bundle_repo.get_owned.return_value = SimpleNamespace(id=1, name="My Bundle", description="Опис")
    skill_repo = AsyncMock()
    skill_repo.list_with_content_for_bundle.return_value = [
        make_skill(1, "alpha", content="A", content_hash="ha"),
        make_skill(2, "beta", content="B", content_hash="hb"),
    ]
    effective = AsyncMock()
    effective.get_effective_for_user.return_value = EffectiveBundle(
        bundle_id=1, agent_id=9, agent_name="Agent",
        skills=(EffectiveSkill(1, "alpha", "ha", False), EffectiveSkill(2, "beta", "hb", True)),
        tools=(EffectiveTool(10, "t", "https://x.io", "none", False, True),),
        packs=(EffectivePack(20, "slug", 2, False),),
        version_hash="vh",
    )
    return bundle_repo, skill_repo, effective


@pytest.fixture
def service(repos):
    return BundleExportService(*repos)


def open_zip(export):
    return zipfile.ZipFile(io.BytesIO(export.content))


class TestBuildZip:
    async def test_raises_when_bundle_not_owned(self, service, repos):
        repos[0].get_owned.return_value = None

        with pytest.raises(NotFoundError, match="Config bundle not found"):
            await service.build_zip(1, 5)

        repos[2].get_effective_for_user.assert_not_awaited()

    async def test_result_metadata(self, service):
        export = await service.build_zip(1, 5)

        assert export.filename == "my-bundle.zip"
        assert export.version_hash == "vh"

    async def test_archive_contains_manifest_and_skill_files(self, service):
        export = await service.build_zip(1, 5)

        with open_zip(export) as z:
            assert sorted(z.namelist()) == [
                "agent.json", "skills/alpha-1/SKILL.md", "skills/beta-2/SKILL.md",
            ]
            assert z.read("skills/alpha-1/SKILL.md").decode() == "---\nname: alpha\n---\nA"

    async def test_manifest_content(self, service):
        export = await service.build_zip(1, 5)

        with open_zip(export) as z:
            manifest = json.loads(z.read("agent.json"))

        assert manifest["schema_version"] == EXPORT_SCHEMA_VERSION
        assert manifest["bundle"] == {"id": 1, "name": "My Bundle", "description": "Опис"}
        assert manifest["agent_profile"] == {"id": 9, "name": "Agent"}
        assert manifest["version_hash"] == "vh"
        assert manifest["skills"] == [
            {"id": 1, "dir": "alpha-1", "path": "skills/alpha-1/SKILL.md",
             "content_hash": "ha", "archived": False},
            {"id": 2, "dir": "beta-2", "path": "skills/beta-2/SKILL.md",
             "content_hash": "hb", "archived": True},
        ]
        assert manifest["tools"] == [
            {"id": 10, "name": "t", "url": "https://x.io", "auth_type": "none",
             "archived": False, "custom": True}
        ]
        assert manifest["knowledge_packs"] == [
            {"id": 20, "slug": "slug", "version": 2, "archived": False}
        ]

    async def test_manifest_keeps_non_ascii_readable(self, service):
        export = await service.build_zip(1, 5)

        with open_zip(export) as z:
            assert "Опис" in z.read("agent.json").decode("utf-8")

    async def test_skill_missing_from_effective_is_not_archived(self, service, repos):
        repos[1].list_with_content_for_bundle.return_value = [make_skill(3, "gamma")]

        export = await service.build_zip(1, 5)

        with open_zip(export) as z:
            manifest = json.loads(z.read("agent.json"))
        assert manifest["skills"][0]["archived"] is False

    async def test_bundle_without_skills(self, service, repos):
        repos[1].list_with_content_for_bundle.return_value = []

        export = await service.build_zip(1, 5)

        with open_zip(export) as z:
            assert z.namelist() == ["agent.json"]

    async def test_output_is_deterministic(self, service):
        first = await service.build_zip(1, 5)
        second = await service.build_zip(1, 5)

        assert first.content == second.content

    async def test_entries_use_fixed_timestamp(self, service):
        export = await service.build_zip(1, 5)

        with open_zip(export) as z:
            assert {i.date_time for i in z.infolist()} == {FIXED_ZIP_TIMESTAMP}