import asyncio
from datetime import datetime, timezone

import pytest

pytest.importorskip("aiosqlite")
skills_mod = pytest.importorskip("src.db.models.skills")
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from src.db.enums.skill_visibility import SkillVisibility  # noqa: E402
from src.repositories.skill_repo import SkillRepository  # noqa: E402

Skill = skills_mod.Skill
PRIVATE = getattr(SkillVisibility, "PRIVATE", None)


def _make_skill(name, owner_id, visibility, archived=False):
    return Skill(
        skill_name=name,
        description=f"{name} description",
        content=f"# {name}",
        owner_id=owner_id,
        visibility=visibility,
        archived_at=datetime.now(timezone.utc) if archived else None,
    )


def test_candidates_and_visible_many_never_leak_private_skills():
    if PRIVATE is None:
        pytest.skip("SkillVisibility.PRIVATE not found; adjust the enum member name")

    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(lambda c: Skill.__table__.create(c))
        except SQLAlchemyError as e:
            pytest.skip(f"Skill table cannot be created on SQLite: {e}")

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add_all(
                [
                    _make_skill("global-active", None, SkillVisibility.GLOBAL),
                    _make_skill("global-archived", None, SkillVisibility.GLOBAL, archived=True),
                    _make_skill("private-of-1", 1, PRIVATE),
                    _make_skill("private-of-2", 2, PRIVATE),
                    _make_skill("private-of-1-archived", 1, PRIVATE, archived=True),
                ]
            )
            try:
                await session.commit()
            except SQLAlchemyError as e:
                pytest.skip(f"Adjust _make_skill() to your NOT NULL columns: {e}")

            repo = SkillRepository(session)

            async def names(viewer):
                return {r.skill_name for r in await repo.list_candidates(viewer)}

            assert await names(1) == {"global-active", "private-of-1"}
            assert await names(2) == {"global-active", "private-of-2"}
            assert await names(3) == {"global-active"}

            rows = await repo.list_candidates(2)
            private_of_2_id = next(r.id for r in rows if r.skill_name == "private-of-2")
            assert await repo.get_visible_many([private_of_2_id], viewer_id=1) == []
            assert [s.skill_name for s in await repo.get_visible_many([private_of_2_id], viewer_id=2)] == [
                "private-of-2"
            ]

            assert await repo.count_candidates(1) == 2
        await engine.dispose()

    asyncio.run(scenario())