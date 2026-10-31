import asyncio
from types import SimpleNamespace as Row

from src.catalog.hint.candidate_collector import CandidateCollector
from src.catalog.hint.models import CandidateKind


class FakeViewerRepo:
    """Skills and tools are per-viewer: list_candidates(viewer_id)."""

    def __init__(self, rows_by_viewer):
        self.rows_by_viewer = rows_by_viewer
        self.calls: list[int] = []

    async def list_candidates(self, viewer_id):
        self.calls.append(viewer_id)
        return self.rows_by_viewer.get(viewer_id, [])


class FakeGlobalRepo:
    """Profiles and packs are global: list_candidates() with no viewer."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    async def list_candidates(self):
        self.calls += 1
        return self.rows


def _skill(id_, name):
    return Row(id=id_, skill_name=name, description=f"{name} d")


def _tool(id_, name):
    return Row(id=id_, tool_name=name, description=f"{name} d")


def _collector(skill_rows=None, tool_rows=None):
    skill_repo = FakeViewerRepo(
        skill_rows
        or {
            1: [_skill(1, "global"), _skill(10, "private-of-1")],
            2: [_skill(1, "global"), _skill(20, "private-of-2")],
        }
    )
    tool_repo = FakeViewerRepo(
        tool_rows
        or {
            1: [_tool(1, "Docker"), _tool(10, "private-tool-of-1")],
            2: [_tool(1, "Docker"), _tool(20, "private-tool-of-2")],
        }
    )
    agent_repo = FakeGlobalRepo([Row(id=1, agent_name="Architect", description="a")])
    pack_repo = FakeGlobalRepo([Row(id=1, name="Docker Docs", description="p")])
    collector = CandidateCollector(
        skill_repo=skill_repo, tool_repo=tool_repo, pack_repo=pack_repo, agent_repo=agent_repo
    )
    return collector, skill_repo, tool_repo, pack_repo, agent_repo


def _names(cands, kind):
    return {c.name for c in cands if c.kind == kind}


def test_viewer_id_is_forwarded_and_skills_are_not_mixed_between_viewers():
    collector, skill_repo, *_ = _collector()

    c1 = asyncio.run(collector.collect(1))
    c2 = asyncio.run(collector.collect(2))

    assert skill_repo.calls == [1, 2]
    assert _names(c1, CandidateKind.SKILL) == {"global", "private-of-1"}
    assert _names(c2, CandidateKind.SKILL) == {"global", "private-of-2"}
    assert "private-of-2" not in {c.name for c in c1}


def test_viewer_id_is_forwarded_and_tools_are_not_mixed_between_viewers():
    collector, _, tool_repo, *_ = _collector()

    c1 = asyncio.run(collector.collect(1))
    c2 = asyncio.run(collector.collect(2))

    assert tool_repo.calls == [1, 2]
    assert _names(c1, CandidateKind.TOOL) == {"Docker", "private-tool-of-1"}
    assert _names(c2, CandidateKind.TOOL) == {"Docker", "private-tool-of-2"}
    assert "private-tool-of-2" not in {c.name for c in c1}


def test_keys_kinds_and_order():
    collector, *_ = _collector()
    cands = asyncio.run(collector.collect(1))

    assert [c.kind for c in cands] == [
        CandidateKind.PROFILE,
        CandidateKind.SKILL,
        CandidateKind.SKILL,
        CandidateKind.TOOL,
        CandidateKind.TOOL,
        CandidateKind.PACK,
    ]
    assert [c.key for c in cands] == [
        "profile:1", "skill:1", "skill:10", "tool:1", "tool:10", "pack:1",
    ]
    assert all(c.key == f"{c.kind.value}:{c.entity_id}" for c in cands)


def test_global_repos_are_queried_once_per_collect():
    collector, skill_repo, tool_repo, pack_repo, agent_repo = _collector()
    asyncio.run(collector.collect(1))
    assert (pack_repo.calls, agent_repo.calls) == (1, 1)
    assert (skill_repo.calls, tool_repo.calls) == ([1], [1])


def test_viewer_without_private_items_sees_only_global_ones():
    collector, *_ = _collector()
    cands = asyncio.run(collector.collect(99))
    assert _names(cands, CandidateKind.SKILL) == set()
    assert _names(cands, CandidateKind.TOOL) == set()
    assert _names(cands, CandidateKind.PROFILE) == {"Architect"}
    assert _names(cands, CandidateKind.PACK) == {"Docker Docs"}


def test_empty_catalog_gives_empty_list():
    empty_global = FakeGlobalRepo([])
    collector = CandidateCollector(
        skill_repo=FakeViewerRepo({}),
        tool_repo=FakeViewerRepo({}),
        pack_repo=empty_global,
        agent_repo=empty_global,
    )
    assert asyncio.run(collector.collect(1)) == []
