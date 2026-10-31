from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from src.db.enums.skill_visibility import SkillVisibility
from src.db.models.skill_usage_events import SkillUsageEvent
from src.repositories.skill_repo import SkillRepository

pytestmark = pytest.mark.db


def archived():
    return datetime.now(timezone.utc)


@pytest.fixture
def skill_repo(db_session):
    return SkillRepository(db_session)


class TestDisabledMethods:

    async def test_get_by_id_is_disabled(self, skill_repo):
        with pytest.raises(NotImplementedError):
            await skill_repo.get_by_id(1)

    async def test_get_all_is_disabled(self, skill_repo):
        with pytest.raises(NotImplementedError):
            await skill_repo.get_all()


class TestVisibility:

    async def test_list_visible_returns_global_and_own_private_only(
        self, skill_repo, make_user, make_skill
    ):
        viewer = await make_user()
        other = await make_user()
        global_skill = await make_skill()
        mine = await make_skill(owner=viewer)
        await make_skill(owner=other)

        result = await skill_repo.list_visible(viewer.id)

        assert {s.id for s in result} == {global_skill.id, mine.id}

    async def test_list_visible_excludes_archived(self, skill_repo, make_user, make_skill):
        viewer = await make_user()
        active = await make_skill()
        await make_skill(archived_at=archived())
        await make_skill(owner=viewer, archived_at=archived())

        result = await skill_repo.list_visible(viewer.id)

        assert {s.id for s in result} == {active.id}

    async def test_pending_review_is_visible_to_owner_only(
        self, skill_repo, make_user, make_skill
    ):
        owner = await make_user()
        stranger = await make_user()
        skill = await make_skill(owner=owner, visibility=SkillVisibility.PENDING_REVIEW)

        assert skill.id in {s.id for s in await skill_repo.list_visible(owner.id)}
        assert skill.id not in {s.id for s in await skill_repo.list_visible(stranger.id)}

    async def test_list_visible_orders_by_name_and_paginates(
        self, skill_repo, make_user, make_skill
    ):
        viewer = await make_user()
        await make_skill(skill_name="b-skill")
        await make_skill(skill_name="a-skill")
        await make_skill(skill_name="c-skill")

        page = await skill_repo.list_visible(viewer.id, limit=2, offset=1)

        assert [s.skill_name for s in page] == ["b-skill", "c-skill"]

    async def test_list_visible_filters_by_domain(
        self, skill_repo, make_user, make_skill, sample_knowledge_domain
    ):
        viewer = await make_user()
        in_domain = await make_skill()
        await make_skill()
        await skill_repo.add_domain(in_domain, sample_knowledge_domain)

        result = await skill_repo.list_visible(viewer.id, domain_id=sample_knowledge_domain.id)

        assert [s.id for s in result] == [in_domain.id]

    async def test_list_visible_does_not_load_content(
        self, db_session, skill_repo, make_user, make_skill
    ):
        viewer = await make_user()
        await make_skill()
        db_session.expunge_all()

        result = await skill_repo.list_visible(viewer.id)

        assert "content" in inspect(result[0]).unloaded

    async def test_get_visible(self, skill_repo, make_user, make_skill):
        viewer = await make_user()
        other = await make_user()
        global_skill = await make_skill()
        mine = await make_skill(owner=viewer)
        theirs = await make_skill(owner=other)
        gone = await make_skill(archived_at=archived())

        assert (await skill_repo.get_visible(global_skill.id, viewer.id)).id == global_skill.id
        assert (await skill_repo.get_visible(mine.id, viewer.id)).id == mine.id
        assert await skill_repo.get_visible(theirs.id, viewer.id) is None
        assert await skill_repo.get_visible(gone.id, viewer.id) is None

    async def test_get_visible_many_filters_invisible_and_handles_empty_input(
        self, skill_repo, make_user, make_skill
    ):
        viewer = await make_user()
        other = await make_user()
        global_skill = await make_skill()
        theirs = await make_skill(owner=other)

        result = await skill_repo.get_visible_many(
            [global_skill.id, global_skill.id, theirs.id], viewer.id
        )

        assert [s.id for s in result] == [global_skill.id]
        assert await skill_repo.get_visible_many([], viewer.id) == []

    async def test_list_and_count_candidates(self, skill_repo, make_user, make_skill):
        viewer = await make_user()
        other = await make_user()
        first = await make_skill(description="first")
        second = await make_skill(owner=viewer, description="second")
        await make_skill(owner=other)
        await make_skill(archived_at=archived())

        rows = await skill_repo.list_candidates(viewer.id)

        assert [(r.id, r.description) for r in rows] == [
            (first.id, "first"),
            (second.id, "second"),
        ]
        assert await skill_repo.count_candidates(viewer.id) == 2

    async def test_get_global_active_many(self, skill_repo, make_user, make_skill):
        owner = await make_user()
        active = await make_skill()
        private = await make_skill(owner=owner)
        old = await make_skill(archived_at=archived())

        result = await skill_repo.get_global_active_many([active.id, private.id, old.id])

        assert [s.id for s in result] == [active.id]
        assert await skill_repo.get_global_active_many([]) == []


class TestEffectiveSetForBundle:

    @pytest_asyncio.fixture
    async def scene(self, db_session, make_user, make_agent, make_bundle, make_skill):
        user = await make_user()
        agent = await make_agent()
        other_agent = await make_agent()
        bundle = await make_bundle(user, agent)

        direct = await make_skill()
        via_profile = await make_skill()
        in_both = await make_skill()
        unrelated = await make_skill()
        other_profile_only = await make_skill()

        bundle.skills.extend([direct, in_both])
        agent.skills.extend([via_profile, in_both])
        other_agent.skills.append(other_profile_only)
        await db_session.commit()

        return dict(
            bundle=bundle,
            direct=direct,
            via_profile=via_profile,
            in_both=in_both,
            unrelated=unrelated,
            other_profile_only=other_profile_only,
        )

    async def test_list_for_bundle_merges_direct_and_profile_skills_without_duplicates(
        self, skill_repo, scene
    ):
        result = await skill_repo.list_for_bundle(scene["bundle"].id)

        ids = [s.id for s in result]
        assert sorted(ids) == sorted(
            [scene["direct"].id, scene["via_profile"].id, scene["in_both"].id]
        )
        assert len(ids) == len(set(ids))

    async def test_get_for_bundle(self, skill_repo, scene):
        bundle_id = scene["bundle"].id

        assert (await skill_repo.get_for_bundle(scene["via_profile"].id, bundle_id)) is not None
        assert await skill_repo.get_for_bundle(scene["unrelated"].id, bundle_id) is None
        assert await skill_repo.get_for_bundle(scene["other_profile_only"].id, bundle_id) is None

    async def test_archived_skills_stay_in_bundle_and_are_flagged_in_manifest(
        self, db_session, skill_repo, scene
    ):
        scene["direct"].archived_at = archived()
        await db_session.commit()

        rows = await skill_repo.list_manifest_for_bundle(scene["bundle"].id)

        by_id = {r.id: r for r in rows}
        assert by_id[scene["direct"].id].archived_at is not None
        assert by_id[scene["via_profile"].id].archived_at is None
        assert by_id[scene["direct"].id].content_hash == scene["direct"].content_hash

    async def test_manifest_is_ordered_by_id(self, skill_repo, scene):
        rows = await skill_repo.list_manifest_for_bundle(scene["bundle"].id)

        assert [r.id for r in rows] == sorted(r.id for r in rows)

    async def test_list_for_bundle_defers_content_but_with_content_loads_it(
        self, db_session, skill_repo, scene
    ):
        bundle_id = scene["bundle"].id
        db_session.expunge_all()

        light = await skill_repo.list_for_bundle(bundle_id)
        assert all("content" in inspect(s).unloaded for s in light)

        db_session.expunge_all()
        full = await skill_repo.list_with_content_for_bundle(bundle_id)
        assert all("content" not in inspect(s).unloaded for s in full)
        assert [s.id for s in full] == sorted(s.id for s in full)


class TestAdminAndOwnerQueries:

    async def test_admin_get_by_id_sees_private_and_archived(
        self, skill_repo, make_user, make_skill
    ):
        owner = await make_user()
        private = await make_skill(owner=owner, archived_at=archived())

        assert (await skill_repo.admin_get_by_id(private.id)).id == private.id
        assert await skill_repo.admin_get_by_id(999999) is None

    async def test_admin_list_global_excludes_private_and_archived_by_default(
        self, skill_repo, make_user, make_skill
    ):
        owner = await make_user()
        active = await make_skill()
        old = await make_skill(archived_at=archived())
        await make_skill(owner=owner)

        default = await skill_repo.admin_list_global()
        with_archived = await skill_repo.admin_list_global(include_archived=True)

        assert {s.id for s in default} == {active.id}
        assert {s.id for s in with_archived} == {active.id, old.id}

    async def test_get_owned_by_id_checks_owner(self, skill_repo, make_user, make_skill):
        owner = await make_user()
        other = await make_user()
        skill = await make_skill(owner=owner)

        assert (await skill_repo.get_owned_by_id(skill.id, owner.id)).id == skill.id
        assert await skill_repo.get_owned_by_id(skill.id, other.id) is None

    async def test_list_owned_and_count_owned_active(self, skill_repo, make_user, make_skill):
        owner = await make_user()
        other = await make_user()
        active = await make_skill(owner=owner)
        old = await make_skill(owner=owner, archived_at=archived())
        await make_skill(owner=other)

        default = await skill_repo.list_owned(owner.id)
        with_archived = await skill_repo.list_owned(owner.id, include_archived=True)

        assert {s.id for s in default} == {active.id}
        assert {s.id for s in with_archived} == {active.id, old.id}
        assert await skill_repo.count_owned_active(owner.id) == 1

    async def test_name_lookups_do_not_mix_global_and_private(
        self, skill_repo, make_user, make_skill
    ):
        owner = await make_user()
        other = await make_user()
        global_skill = await make_skill(skill_name="shared-name")
        private = await make_skill(owner=owner, skill_name="shared-name")

        assert (await skill_repo.get_global_by_name("shared-name")).id == global_skill.id
        assert (await skill_repo.get_owned_by_name("shared-name", owner.id)).id == private.id
        assert await skill_repo.get_owned_by_name("shared-name", other.id) is None
        assert await skill_repo.get_global_by_name("missing") is None


class TestArchiveAndRestore:

    async def test_archive_sets_timestamp_once(self, skill_repo, make_skill):
        skill = await make_skill()

        await skill_repo.archive(skill)
        first = skill.archived_at
        await skill_repo.archive(skill)

        assert first is not None
        assert skill.archived_at == first

    async def test_restore_clears_timestamp_and_is_noop_for_active(self, skill_repo, make_skill):
        skill = await make_skill(archived_at=archived())

        await skill_repo.restore(skill)
        assert skill.archived_at is None

        await skill_repo.restore(skill)
        assert skill.archived_at is None


class TestRecordSelection:

    async def test_increments_counter_and_writes_event(
        self, db_session, skill_repo, make_user, make_skill
    ):
        user = await make_user()
        skill = await make_skill()

        await skill_repo.record_selection(skill.id, user.id)
        result = await skill_repo.record_selection(skill.id, user.id)

        assert result.id == skill.id
        assert skill.skill_selected_freq == 2
        events = (
            await db_session.execute(
                select(SkillUsageEvent).where(SkillUsageEvent.skill_id == skill.id)
            )
        ).scalars().all()
        assert len(events) == 2

    async def test_event_keeps_config_bundle_id(
        self, db_session, skill_repo, make_user, make_agent, make_bundle, make_skill
    ):
        user = await make_user()
        bundle = await make_bundle(user, await make_agent())
        skill = await make_skill()

        await skill_repo.record_selection(skill.id, user.id, config_bundle_id=bundle.id)

        event = (
            await db_session.execute(
                select(SkillUsageEvent).where(SkillUsageEvent.skill_id == skill.id)
            )
        ).scalar_one()
        assert event.config_bundle_id == bundle.id

    async def test_unknown_skill_fails_on_flush(self, db_session, skill_repo, make_user):
        user = await make_user()

        with pytest.raises(IntegrityError):
            await skill_repo.record_selection(999999, user.id)

        await db_session.rollback()


class TestAddDomain:

    async def test_appends_once(
        self, skill_repo, make_skill, sample_knowledge_domain
    ):
        skill = await make_skill()

        await skill_repo.add_domain(skill, sample_knowledge_domain)
        await skill_repo.add_domain(skill, sample_knowledge_domain)

        assert [d.id for d in skill.domains] == [sample_knowledge_domain.id]

    async def test_allows_multiple_domains(
        self, skill_repo, make_skill, sample_knowledge_domain, another_knowledge_domain
    ):
        skill = await make_skill()

        await skill_repo.add_domain(skill, sample_knowledge_domain)
        await skill_repo.add_domain(skill, another_knowledge_domain)

        assert {d.id for d in skill.domains} == {
            sample_knowledge_domain.id,
            another_knowledge_domain.id,
        }