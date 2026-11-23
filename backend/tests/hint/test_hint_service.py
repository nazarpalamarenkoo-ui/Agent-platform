import asyncio
from types import SimpleNamespace as Row

import pytest

from src.catalog.hint.candidate_collector import CandidateCollector
from src.catalog.hint.catalog_hint_service import MAX_INTENT_CHARS, CatalogHintService
from src.catalog.hint.exceptions import HintClientError, HintValidationError
from src.catalog.hint.models import CandidateKind, CatalogCandidate, GapKind
from src.rag.retrieval.agentic.exceptions import (
    LLMClientError,
    LLMParseError,
    LLMRateLimitError,
)


class ScriptedLLM:
    """Returns / raises the next scripted item on every call."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls: list[dict] = []

    async def complete_json(self, prompt, system):
        self.calls.append({"prompt": prompt, "system": system})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeCollector:
    def __init__(self, candidates):
        self.candidates = candidates
        self.viewers: list[int] = []

    async def collect(self, viewer_id):
        self.viewers.append(viewer_id)
        return self.candidates


class FakeRepo:
    """Covers get_active / get_visible_many / get_active_many."""

    def __init__(self, rows):
        self.rows = {r.id: r for r in rows}
        self.calls: list[tuple] = []

    async def get_active(self, id_):
        self.calls.append(("get_active", id_))
        return self.rows.get(id_)

    async def get_visible_many(self, ids, viewer_id):
        self.calls.append(("get_visible_many", list(ids), viewer_id))
        return [self.rows[i] for i in sorted(ids) if i in self.rows]  # DB order != LLM order

    async def get_active_many(self, ids):
        self.calls.append(("get_active_many", list(ids)))
        return [self.rows[i] for i in sorted(ids) if i in self.rows]


def _cand(kind, id_, name):
    return CatalogCandidate(
        key=CatalogCandidate.build_key(kind, id_),
        kind=kind,
        entity_id=id_,
        name=name,
        description=f"{name} description",
    )


CANDIDATES = [
    _cand(CandidateKind.PROFILE, 1, "Architect"),
    _cand(CandidateKind.SKILL, 1, "UML Diagrams"),
    _cand(CandidateKind.SKILL, 2, "Docker Basics"),
    _cand(CandidateKind.SKILL, 3, "System Design"),
    _cand(CandidateKind.TOOL, 1, "Docker"),
    _cand(CandidateKind.TOOL, 2, "UML Renderer"),
    _cand(CandidateKind.PACK, 1, "Docker Documentation"),
]


def _skill(id_, name):
    return Row(id=id_, skill_name=name, description=f"{name} description")


def _tool(id_, name):
    return Row(id=id_, tool_name=name, description=f"{name} description")


def _pack(id_, name):
    return Row(id=id_, name=name, description=f"{name} description")


def _agent(skill_ids=(), tool_ids=()):
    return Row(
        id=1,
        agent_name="Architect",
        description="Designs systems",
        skills=[Row(id=i) for i in skill_ids],
        tools=[Row(id=i) for i in tool_ids],
    )


def _selection(**kw):
    base = {
        "profile_key": None,
        "skill_keys": [],
        "tool_keys": [],
        "knowledge_pack_keys": [],
        "gaps": [],
        "reasoning": "because",
    }
    base.update(kw)
    return base


def _service(llm, candidates=CANDIDATES, agent=None, max_retries=1):
    repos = {
        "skill_repo": FakeRepo([_skill(1, "UML Diagrams"), _skill(2, "Docker Basics"), _skill(3, "System Design")]),
        "tool_repo": FakeRepo([_tool(1, "Docker"), _tool(2, "UML Renderer")]),
        "pack_repo": FakeRepo([_pack(1, "Docker Documentation")]),
        "agent_repo": FakeRepo([agent] if agent else [_agent()]),
    }
    collector = FakeCollector(candidates)
    service = CatalogHintService(
        llm_client=llm, candidate_collector=collector, max_retries=max_retries, **repos
    )
    return service, collector, repos


def run(coro):
    return asyncio.run(coro)

@pytest.mark.parametrize("intent", ["", "   ", "\n\t"])
def test_blank_intent_is_rejected_before_any_work(intent):
    llm = ScriptedLLM()
    service, collector, _ = _service(llm)
    with pytest.raises(ValueError, match="empty"):
        run(service.propose(1, intent))
    assert collector.viewers == [] and llm.calls == []


def test_too_long_intent_is_rejected():
    service, collector, _ = _service(ScriptedLLM())
    with pytest.raises(ValueError, match=str(MAX_INTENT_CHARS)):
        run(service.propose(1, "x" * (MAX_INTENT_CHARS + 1)))
    assert collector.viewers == []


def test_intent_at_the_limit_is_accepted():
    service, *_ = _service(ScriptedLLM(_selection()))
    run(service.propose(1, "x" * MAX_INTENT_CHARS))


def test_empty_catalog_short_circuits_without_calling_llm():
    llm = ScriptedLLM()
    service, *_ = _service(llm, candidates=[])
    proposal = run(service.propose(1, "anything"))
    assert llm.calls == []
    assert proposal.reasoning == "Catalog is currently empty."
    assert proposal.skills == proposal.tools == proposal.knowledge_packs == []
    assert proposal.agent_profile is None and proposal.gaps == []

def test_prompt_contains_intent_and_every_candidate_key_with_its_section():
    service, *_ = _service(ScriptedLLM())
    prompt = service._build_prompt("  draw UML  ", CANDIDATES)

    assert prompt.startswith("User request: draw UML\n")
    for c in CANDIDATES:
        assert f"- {c.key}: {c.name} — {c.description}" in prompt
    for title in ("## Agent Profiles", "## Skills", "## Tools", "## Knowledge Packs"):
        assert title in prompt
    assert prompt.index("## Agent Profiles") < prompt.index("## Skills") < prompt.index("## Tools") < prompt.index("## Knowledge Packs")


def test_empty_sections_are_marked_not_omitted():
    service, *_ = _service(ScriptedLLM())
    only_skills = [c for c in CANDIDATES if c.kind == CandidateKind.SKILL]
    prompt = service._build_prompt("x", only_skills)
    assert prompt.count("(none available)") == 3


def test_system_prompt_is_passed_and_mentions_gaps():
    llm = ScriptedLLM(_selection())
    service, *_ = _service(llm)
    run(service.propose(1, "x"))
    assert "gaps" in llm.calls[0]["system"]


def test_viewer_id_reaches_the_collector():
    service, collector, _ = _service(ScriptedLLM(_selection()))
    run(service.propose(42, "x"))
    assert collector.viewers == [42]

def test_invalid_key_then_valid_answer_succeeds_on_retry():
    llm = ScriptedLLM(_selection(skill_keys=["skill:999"]), _selection(skill_keys=["skill:1"]))
    service, *_ = _service(llm)
    proposal = run(service.propose(1, "x"))
    assert len(llm.calls) == 2
    assert [s["name"] for s in proposal.skills] == ["UML Diagrams"]


def test_llm_parse_error_is_retried():
    llm = ScriptedLLM(LLMParseError("bad json"), _selection())
    service, *_ = _service(llm)
    run(service.propose(1, "x"))
    assert len(llm.calls) == 2


def test_retries_are_exhausted_into_validation_error():
    llm = ScriptedLLM(*[_selection(skill_keys=["skill:999"])] * 2)
    service, *_ = _service(llm, max_retries=1)
    with pytest.raises(HintValidationError, match="skill:999"):
        run(service.propose(1, "x"))
    assert len(llm.calls) == 2


def test_max_retries_zero_means_a_single_attempt():
    llm = ScriptedLLM(_selection(skill_keys=["skill:999"]))
    service, *_ = _service(llm, max_retries=0)
    with pytest.raises(HintValidationError):
        run(service.propose(1, "x"))
    assert len(llm.calls) == 1


def test_rate_limit_is_not_retried_and_becomes_client_error():
    llm = ScriptedLLM(LLMRateLimitError("429"), _selection())
    service, *_ = _service(llm)
    with pytest.raises(HintClientError, match="rate limit"):
        run(service.propose(1, "x"))
    assert len(llm.calls) == 1


def test_provider_error_is_not_retried_and_becomes_client_error():
    llm = ScriptedLLM(LLMClientError("boom"), _selection())
    service, *_ = _service(llm)
    with pytest.raises(HintClientError, match="provider"):
        run(service.propose(1, "x"))
    assert len(llm.calls) == 1

def test_proposal_is_expanded_into_catalog_rows_in_the_llm_order():
    llm = ScriptedLLM(
        _selection(
            profile_key="profile:1",
            skill_keys=["skill:2", "skill:1"],
            tool_keys=["tool:2", "tool:1"],
            knowledge_pack_keys=["pack:1"],
        )
    )
    service, *_ = _service(llm)
    p = run(service.propose(1, "x"))

    assert p.agent_profile == {"id": 1, "name": "Architect", "description": "Designs systems"}
    assert [s["id"] for s in p.skills] == [2, 1]
    assert [t["id"] for t in p.tools] == [2, 1]
    assert [k["id"] for k in p.knowledge_packs] == [1]
    assert p.skills[0] == {"id": 2, "name": "Docker Basics", "description": "Docker Basics description"}
    assert p.reasoning == "because"


def test_skills_and_tools_already_in_the_profile_are_not_proposed_again():
    llm = ScriptedLLM(
        _selection(
            profile_key="profile:1",
            skill_keys=["skill:1", "skill:2"],
            tool_keys=["tool:1", "tool:2"],
        )
    )
    service, *_ = _service(llm, agent=_agent(skill_ids=[1], tool_ids=[2]))
    p = run(service.propose(1, "x"))
    assert [s["id"] for s in p.skills] == [2]
    assert [t["id"] for t in p.tools] == [1]


def test_nothing_is_filtered_when_no_profile_is_chosen():
    llm = ScriptedLLM(_selection(skill_keys=["skill:1"]))
    service, _, repos = _service(llm, agent=_agent(skill_ids=[1]))
    p = run(service.propose(1, "x"))
    assert [s["id"] for s in p.skills] == [1]
    assert p.agent_profile is None
    assert repos["agent_repo"].calls == []


def test_profile_that_disappeared_is_ignored_and_nothing_inherited():
    llm = ScriptedLLM(_selection(profile_key="profile:1", skill_keys=["skill:1"]))
    service, _, repos = _service(llm, agent=_agent(skill_ids=[1]))
    repos["agent_repo"].rows.clear()  # deleted between collect() and expand
    p = run(service.propose(1, "x"))
    assert p.agent_profile is None
    assert [s["id"] for s in p.skills] == [1]


def test_items_the_viewer_can_no_longer_see_are_dropped_silently():
    llm = ScriptedLLM(_selection(skill_keys=["skill:1", "skill:3"], tool_keys=["tool:1"]))
    service, _, repos = _service(llm)
    del repos["skill_repo"].rows[3]
    del repos["tool_repo"].rows[1]
    p = run(service.propose(1, "x"))
    assert [s["id"] for s in p.skills] == [1]
    assert p.tools == []


def test_viewer_id_is_used_for_visibility_checks():
    llm = ScriptedLLM(_selection(skill_keys=["skill:1"], tool_keys=["tool:1"]))
    service, _, repos = _service(llm)
    run(service.propose(7, "x"))
    assert ("get_visible_many", [1], 7) in repos["skill_repo"].calls
    assert ("get_visible_many", [1], 7) in repos["tool_repo"].calls


def test_gaps_are_passed_through_to_the_proposal():
    llm = ScriptedLLM(
        _selection(gaps=[{"kind": "tool", "name": "Terraform", "description": "IaC", "reason": "none"}])
    )
    service, *_ = _service(llm)
    p = run(service.propose(1, "need terraform"))
    assert [(g.kind, g.name) for g in p.gaps] == [(GapKind.TOOL, "Terraform")]


def test_gap_naming_an_existing_entry_is_filtered_by_the_parser():
    llm = ScriptedLLM(_selection(gaps=[{"kind": "skill", "name": "uml diagrams"}]))
    service, *_ = _service(llm)
    assert run(service.propose(1, "x")).gaps == []


def test_honest_empty_answer_gives_an_empty_proposal():
    service, *_ = _service(ScriptedLLM(_selection()))
    p = run(service.propose(1, "borscht"))
    assert p.agent_profile is None
    assert p.skills == p.tools == p.knowledge_packs == p.gaps == []
    assert p.generated_skill is None


class FakeKnowledgeService:
    def __init__(self, hits):
        self.hits = hits
        self.calls: list[dict] = []

    async def search_by_slugs(self, **kwargs):
        self.calls.append(kwargs)
        return self.hits


class FakeDocumentRepo:
    def __init__(self, docs):
        self.docs = {d.id: d for d in docs}

    async def get_by_ids(self, ids):
        return [self.docs[i] for i in ids if i in self.docs]


def test_propose_searches_selected_packs_and_generates_grounded_skill_with_sources():
    draft_json = {
        "skill_name": "Docker Compose Guide",
        "description": "Configure and run multi-container Docker applications.",
        "content": "## When to use\nUse for compose stacks.\n\n## Sources\n- Docker Documentation (https://docs.docker.com/compose/)",
    }
    llm = ScriptedLLM(
        _selection(
            profile_key="profile:1",
            knowledge_pack_keys=["pack:1"],
            search_queries=["docker compose service healthcheck"],
        ),
        draft_json,
    )
    knowledge = FakeKnowledgeService(
        [
            Row(
                id="chunk-1",
                score=0.92,
                payload={
                    "knowledge_pack": "docker-docs",
                    "chunk_index": 0,
                    "document_id": 10,
                    "text": "Use healthcheck in compose.yaml to wait for dependencies.",
                    "source_type": "manual",
                },
            )
        ]
    )
    doc_repo = FakeDocumentRepo(
        [Row(id=10, source="https://docs.docker.com/compose/", document_type="manual")]
    )
    service, _, repos = _service(llm)
    repos["pack_repo"].rows[1] = Row(
        id=1,
        slug="docker-docs",
        name="Docker Documentation",
        description="Official Docker docs",
        domain_id=5,
    )
    service.knowledge_service = knowledge
    service.document_repo = doc_repo

    proposal = run(service.propose(1, "configure docker compose healthcheck"))

    assert len(knowledge.calls) == 2
    assert {c["query"] for c in knowledge.calls} == {
        "configure docker compose healthcheck",
        "docker compose service healthcheck",
    }
    assert proposal.generated_skill is not None
    assert proposal.generated_skill.skill_name == "Docker Compose Guide"
    assert proposal.generated_skill.grounded is True
    assert proposal.generated_skill.sources == [
        "Docker Documentation: https://docs.docker.com/compose/"
    ]
    assert len(proposal.generated_skill.used_packs) == 1
    assert proposal.generated_skill.used_packs[0].slug == "docker-docs"
    assert proposal.generated_skill.used_packs[0].chunks == 1


def test_propose_returns_no_generated_skill_when_rag_finds_no_relevant_chunks():
    llm = ScriptedLLM(
        _selection(
            knowledge_pack_keys=["pack:1"],
            search_queries=["unrelated query"],
        )
    )
    knowledge = FakeKnowledgeService([])
    service, _, repos = _service(llm)
    repos["pack_repo"].rows[1] = Row(
        id=1,
        slug="docker-docs",
        name="Docker Documentation",
        description="Official Docker docs",
        domain_id=5,
    )
    service.knowledge_service = knowledge

    proposal = run(service.propose(1, "something not in pack"))

    assert len(llm.calls) == 1
    assert proposal.knowledge_packs == [
        {"id": 1, "name": "Docker Documentation", "description": "Official Docker docs"}
    ]
    assert proposal.generated_skill is None


class FakeTokenRepo:
    def __init__(self, exceeded=False):
        self.exceeded = exceeded
        self.reported: list[tuple[int, int, int | None]] = []

    async def is_user_limit_exceeded(self, user_id: int) -> bool:
        return self.exceeded

    async def report_usage_by_user_id(self, user_id: int, tokens_used: int, agent_id=None):
        self.reported.append((user_id, tokens_used, agent_id))


def test_propose_rejects_when_user_token_limit_exceeded():
    from src.services.errors import ForbiddenError

    llm = ScriptedLLM(_selection())
    service, collector, _ = _service(llm)
    service.token_repo = FakeTokenRepo(exceeded=True)

    with pytest.raises(ForbiddenError, match="Token limit exceeded"):
        run(service.propose(1, "build api"))

    assert collector.viewers == []
    assert llm.calls == []
