import io
import json
import zipfile

import pytest
import pytest_asyncio

from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.services.bundle_export_service import (
    EXPORT_SCHEMA_VERSION,
    BundleExportService,
)
from src.services.effective_bundle_service import EffectiveBundleService
from src.services.errors import NotFoundError


@pytest.fixture
def service(db_session):
    bundle_repo = ConfigBundleRepository(db_session)
    skill_repo = SkillRepository(db_session)
    effective = EffectiveBundleService(
        bundle_repo,
        skill_repo,
        ToolDefinitionRepository(db_session),
        KnowledgePackRepository(db_session),
        AgentProfileRepository(db_session),
    )
    return BundleExportService(bundle_repo, skill_repo, effective)


def _open(export) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(export.content))


@pytest_asyncio.fixture
async def full_bundle(
    db_session, sample_config_bundle, make_skill, sample_tool, sample_knowledge_pack
):
    skill = await make_skill(
        skill_name="exported-skill", description="Exported desc", content="Exported body"
    )
    repo = ConfigBundleRepository(db_session)
    await repo.add_skill(sample_config_bundle, skill)
    await repo.add_tool(sample_config_bundle, sample_tool)
    await repo.add_knowledge_pack(sample_config_bundle, sample_knowledge_pack)
    return sample_config_bundle, skill


class TestBuildZip:
    async def test_archive_contains_manifest_and_skill_files(
        self, service, full_bundle, sample_user
    ):
        bundle, skill = full_bundle

        export = await service.build_zip(bundle.id, sample_user.id)

        with _open(export) as archive:
            names = archive.namelist()
            manifest = json.loads(archive.read("agent.json"))
            [skill_path] = [n for n in names if n.endswith("SKILL.md")]
            skill_text = archive.read(skill_path).decode("utf-8")

        assert "agent.json" in names
        assert skill_path.startswith("skills/")
        assert "exported-skill" in skill_text
        assert "Exported desc" in skill_text
        assert "Exported body" in skill_text

        assert manifest["schema_version"] == EXPORT_SCHEMA_VERSION
        assert manifest["bundle"]["id"] == bundle.id
        assert manifest["bundle"]["name"] == bundle.name
        assert manifest["version_hash"] == export.version_hash
        assert manifest["skills"][0]["id"] == skill.id
        assert manifest["skills"][0]["path"] == skill_path
        assert manifest["skills"][0]["content_hash"] == skill.content_hash
        assert manifest["skills"][0]["archived"] is False

    async def test_manifest_lists_tools_and_packs(
        self, service, full_bundle, sample_user, sample_tool, sample_knowledge_pack
    ):
        bundle, _ = full_bundle

        export = await service.build_zip(bundle.id, sample_user.id)

        with _open(export) as archive:
            manifest = json.loads(archive.read("agent.json"))

        assert sample_tool.id in {t["id"] for t in manifest["tools"]}
        tool = next(t for t in manifest["tools"] if t["id"] == sample_tool.id)
        assert tool["url"] == sample_tool.url
        assert tool["custom"] is False
        assert sample_knowledge_pack.slug in {p["slug"] for p in manifest["knowledge_packs"]}

    async def test_manifest_marks_archived_skill(
        self, service, full_bundle, sample_user, db_session
    ):
        bundle, skill = full_bundle
        await SkillRepository(db_session).archive(skill)

        export = await service.build_zip(bundle.id, sample_user.id)

        with _open(export) as archive:
            manifest = json.loads(archive.read("agent.json"))
        entry = next(s for s in manifest["skills"] if s["id"] == skill.id)
        assert entry["archived"] is True

    async def test_filename_is_derived_from_bundle_name(
        self, service, sample_config_bundle, sample_user
    ):
        export = await service.build_zip(sample_config_bundle.id, sample_user.id)
        assert export.filename.endswith(".zip")
        assert export.filename != ".zip"

    async def test_output_is_deterministic(self, service, full_bundle, sample_user):
        bundle, _ = full_bundle

        first = await service.build_zip(bundle.id, sample_user.id)
        second = await service.build_zip(bundle.id, sample_user.id)

        assert first.content == second.content
        assert first.version_hash == second.version_hash

    async def test_version_hash_changes_when_content_changes(
        self, service, full_bundle, sample_user, make_skill, db_session
    ):
        bundle, _ = full_bundle
        before = await service.build_zip(bundle.id, sample_user.id)

        await ConfigBundleRepository(db_session).add_skill(bundle, await make_skill())
        after = await service.build_zip(bundle.id, sample_user.id)

        assert before.version_hash != after.version_hash
        assert before.content != after.content

    async def test_two_skills_with_same_name_get_distinct_directories(
        self, service, sample_config_bundle, sample_user, make_skill, db_session
    ):
        # global names are unique, so the twin is a global skill + a private one
        repo = ConfigBundleRepository(db_session)
        await repo.add_skill(sample_config_bundle, await make_skill(skill_name="twin"))
        await repo.add_skill(
            sample_config_bundle, await make_skill(owner=sample_user, skill_name="twin")
        )

        export = await service.build_zip(sample_config_bundle.id, sample_user.id)

        with _open(export) as archive:
            skill_files = [n for n in archive.namelist() if n.endswith("SKILL.md")]
        assert len(skill_files) == len(set(skill_files)) == 2

    async def test_empty_bundle_has_only_manifest(
        self, service, sample_config_bundle, sample_user
    ):
        export = await service.build_zip(sample_config_bundle.id, sample_user.id)

        with _open(export) as archive:
            manifest = json.loads(archive.read("agent.json"))
            assert [n for n in archive.namelist() if n.endswith("SKILL.md")] == []
        assert manifest["skills"] == []

    async def test_raises_for_foreign_bundle(
        self, service, sample_config_bundle, another_user
    ):
        with pytest.raises(NotFoundError, match="Config bundle not found"):
            await service.build_zip(sample_config_bundle.id, another_user.id)

    async def test_raises_for_unknown_bundle(self, service, sample_user):
        with pytest.raises(NotFoundError):
            await service.build_zip(999_999, sample_user.id)