import io
import json
import zipfile
from dataclasses import dataclass

from src.catalog.hint.skill_markdown import assign_skill_dirs, render_skill_md, skill_dir_name
from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.skill_repo import SkillRepository
from src.services.effective_bundle_service import EffectiveBundleService
from src.services.errors import NotFoundError

EXPORT_SCHEMA_VERSION = 1
FIXED_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class BundleExport:
    filename: str
    content: bytes
    version_hash: str


class BundleExportService:

    def __init__(
        self,
        config_bundle_repo: ConfigBundleRepository,
        skill_repo: SkillRepository,
        effective_service: EffectiveBundleService,
    ):
        self.config_bundle_repo = config_bundle_repo
        self.skill_repo = skill_repo
        self.effective_service = effective_service

    async def build_zip(self, bundle_id: int, user_id: int) -> BundleExport:
        bundle = await self.config_bundle_repo.get_owned(bundle_id, user_id)
        if bundle is None:
            raise NotFoundError("Config bundle not found")

        effective = await self.effective_service.get_effective_for_user(bundle_id, user_id)
        skills = await self.skill_repo.list_with_content_for_bundle(bundle_id)

        directories = assign_skill_dirs((skill.id, skill.skill_name) for skill in skills)
        entries: list[tuple[str, dict, str]] = []
        for skill in skills:
            text = render_skill_md(skill.skill_name, skill.description, skill.content)
            entries.append(
                (directories[skill.id], {"id": skill.id, "content_hash": skill.content_hash}, text)
            )

        archived = {s.id: s.archived for s in effective.skills}
        manifest = {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "bundle": {
                "id": bundle.id,
                "name": bundle.name,
                "description": bundle.description,
            },
            "agent_profile": {"id": effective.agent_id, "name": effective.agent_name},
            "skills": [
                {
                    "id": meta["id"],
                    "dir": directory,
                    "path": f"skills/{directory}/SKILL.md",
                    "content_hash": meta["content_hash"],
                    "archived": archived.get(meta["id"], False),
                }
                for directory, meta, _ in entries
            ],
            "tools": [
                {
                    "id": t.id,
                    "name": t.name,
                    "url": t.url,
                    "auth_type": t.auth_type,
                    "archived": t.archived,
                    "custom": t.custom,
                }
                for t in effective.tools
            ],
            "knowledge_packs": [
                {"id": p.id, "slug": p.slug, "version": p.version, "archived": p.archived}
                for p in effective.packs
            ],
            "version_hash": effective.version_hash,
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            self._write(archive, "agent.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for directory, _, text in entries:
                self._write(archive, f"skills/{directory}/SKILL.md", text)

        return BundleExport(
            filename=f"{skill_dir_name(bundle.name)}.zip",
            content=buffer.getvalue(),
            version_hash=effective.version_hash,
        )

    @staticmethod
    def _write(archive: zipfile.ZipFile, path: str, text: str) -> None:
        info = zipfile.ZipInfo(path, date_time=FIXED_ZIP_TIMESTAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, text.encode("utf-8"))