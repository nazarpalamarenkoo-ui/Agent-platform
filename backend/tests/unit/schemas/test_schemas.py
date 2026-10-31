from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.db.enums.notification_type import NotificationType
from src.db.enums.skill_visibility import SkillVisibility
from src.db.enums.tool_auth_type import ToolAuthType
from src.db.enums.user_role import UserRole

from src.schemas.admin_skills import (
    AccessLogEntry,
    AdminSkillListItem,
    AdminSkillRead,
    AdminToolItem,
    ArchiveForViolation,
    UserOverview,
)
from src.schemas.agent import CustomAgentCreate, CustomAgentRead
from src.schemas.bundle_ops import (
    BundleItems,
    ConfigBundleUpdate,
    EffectiveBundleRead,
    EffectivePackRead,
    EffectiveSkillRead,
    EffectiveToolRead,
)
from src.schemas.catalog import (
    HintItem,
    HintProfile,
    HintRef,
    HintRequest,
    HintResponse,
)
from src.schemas.catalog_ops import AgentUpdate, SkillUpdate, ToolUpdate
from src.schemas.config_bundle import ConfigBundleClone
from src.schemas.device import DeviceTokenCreate
from src.schemas.knowledge import JobCreatedResponse, JobStatusResponse
from src.schemas.notification import MarkedRead, NotificationRead, UnreadCount
from src.schemas.skill_drafts import (
    AttachPacksRequest,
    AttachPacksResponse,
    PackRef,
    PackSuggestion,
    SkillDraftConfirm,
    SkillDraftJobResponse,
    SkillDraftRequest,
    SkillDraftResult,
    SkillDraftStatus,
    SuggestPacksRequest,
    UsedPack,
)
from src.schemas.user import AdminUserRead, RoleUpdate, TokenLimitUpdate
from src.schemas.user_skills import (
    MySkillCreate,
    MySkillImport,
    MySkillRead,
    MySkillSummary,
    MySkillUpdate,
)
from src.schemas.user_tools import (
    MyToolCreate,
    MyToolRead,
    MyToolResponse,
    MyToolUpdate,
)

NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
VALID_HASH = "a" * 64


def orm_mock(**kwargs) -> MagicMock:
    obj = MagicMock()
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def make(schema, payload, **overrides):
    return schema(**{**payload, **overrides})


def without(payload, field):
    return {k: v for k, v in payload.items() if k != field}

class TestNotificationRead:

    def _orm(self, **overrides):
        base = dict(
            id=1,
            type=next(iter(NotificationType)),
            skill_id=None,
            tool_id=None,
            item_name=None,
            read_at=None,
            created_at=NOW,
        )
        base.update(overrides)
        return orm_mock(**base)

    def test_from_orm_unread_without_item(self):
        data = NotificationRead.model_validate(self._orm())
        assert data.read_at is None
        assert data.skill_id is None
        assert data.tool_id is None
        assert data.item_name is None

    def test_from_orm_with_skill_and_read_at(self):
        data = NotificationRead.model_validate(
            self._orm(skill_id=5, item_name="summarization", read_at=NOW)
        )
        assert data.skill_id == 5
        assert data.item_name == "summarization"
        assert data.read_at == NOW

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError):
            NotificationRead.model_validate(self._orm(type="not-a-type"))

    def test_type_accepts_enum_value(self):
        member = next(iter(NotificationType))
        data = NotificationRead.model_validate(self._orm(type=member.value))
        assert data.type == member

    @pytest.mark.parametrize("field", ["skill_id", "tool_id", "item_name", "read_at"])
    def test_nullable_fields_are_still_required(self, field):
        """They have no default: omitting them must fail (explicit None is OK)."""
        payload = dict(
            id=1, type=next(iter(NotificationType)), skill_id=None, tool_id=None,
            item_name=None, read_at=None, created_at=NOW,
        )
        del payload[field]
        with pytest.raises(ValidationError):
            NotificationRead(**payload)


class TestUnreadCountAndMarkedRead:

    def test_unread_count(self):
        assert UnreadCount(unread=3).unread == 3

    def test_unread_count_missing_raises(self):
        with pytest.raises(ValidationError):
            UnreadCount()

    def test_marked_read(self):
        assert MarkedRead(updated=0).updated == 0

    def test_marked_read_non_int_raises(self):
        with pytest.raises(ValidationError):
            MarkedRead(updated="many")


class TestSkillDraftRequest:

    def test_minimal_defaults(self):
        data = SkillDraftRequest(intent="write a summarizer")
        assert data.skill_name is None
        assert data.description is None
        assert data.source_text is None
        assert data.config_bundle_id is None
        assert data.knowledge_pack_ids == []
        assert data.search_queries == []
        assert data.auto_packs is False

    def test_default_lists_are_not_shared_between_instances(self):
        a = SkillDraftRequest(intent="a")
        b = SkillDraftRequest(intent="b")
        a.knowledge_pack_ids.append(1)
        assert b.knowledge_pack_ids == []

    def test_missing_intent_raises(self):
        with pytest.raises(ValidationError):
            SkillDraftRequest()

    def test_empty_intent_raises(self):
        with pytest.raises(ValidationError):
            SkillDraftRequest(intent="")

    @pytest.mark.parametrize("length,ok", [(2000, True), (2001, False)])
    def test_intent_max_length(self, length, ok):
        if ok:
            assert len(SkillDraftRequest(intent="x" * length).intent) == length
        else:
            with pytest.raises(ValidationError):
                SkillDraftRequest(intent="x" * length)

    @pytest.mark.parametrize(
        "field,limit",
        [("skill_name", 100), ("description", 255), ("source_text", 20_000)],
    )
    def test_optional_text_max_length_boundary(self, field, limit):
        SkillDraftRequest(intent="i", **{field: "x" * limit})
        with pytest.raises(ValidationError):
            SkillDraftRequest(intent="i", **{field: "x" * (limit + 1)})

    def test_knowledge_pack_ids_max_10(self):
        assert len(SkillDraftRequest(intent="i", knowledge_pack_ids=list(range(10))).knowledge_pack_ids) == 10
        with pytest.raises(ValidationError):
            SkillDraftRequest(intent="i", knowledge_pack_ids=list(range(11)))

    def test_search_queries_max_3(self):
        assert len(SkillDraftRequest(intent="i", search_queries=["a", "b", "c"]).search_queries) == 3
        with pytest.raises(ValidationError):
            SkillDraftRequest(intent="i", search_queries=["a", "b", "c", "d"])

    def test_non_int_pack_id_raises(self):
        with pytest.raises(ValidationError):
            SkillDraftRequest(intent="i", knowledge_pack_ids=["abc"])


class TestPackRefAndSuggestions:

    def test_pack_ref_valid(self):
        data = PackRef(id=1, slug="s", name="n", description="d")
        assert data.slug == "s"

    @pytest.mark.parametrize("field", ["id", "slug", "name", "description"])
    def test_pack_ref_missing_field_raises(self, field):
        payload = dict(id=1, slug="s", name="n", description="d")
        with pytest.raises(ValidationError):
            PackRef(**without(payload, field))

    def test_pack_suggestion_defaults(self):
        data = PackSuggestion()
        assert data.packs == []
        assert data.queries == []

    def test_pack_suggestion_builds_nested_packs_from_dicts(self):
        data = PackSuggestion(
            packs=[dict(id=1, slug="s", name="n", description="d")],
            queries=["q"],
        )
        assert isinstance(data.packs[0], PackRef)

    def test_pack_suggestion_invalid_nested_pack_raises(self):
        with pytest.raises(ValidationError):
            PackSuggestion(packs=[{"id": 1}])


class TestSuggestPacksRequest:

    def test_valid(self):
        assert SuggestPacksRequest(intent="x").intent == "x"

    def test_empty_raises(self):
        with pytest.raises(ValidationError):
            SuggestPacksRequest(intent="")

    def test_too_long_raises(self):
        with pytest.raises(ValidationError):
            SuggestPacksRequest(intent="x" * 2001)

    def test_missing_raises(self):
        with pytest.raises(ValidationError):
            SuggestPacksRequest()


class TestSkillDraftJobResponse:

    def test_valid(self):
        data = SkillDraftJobResponse(job_id=1, status="pending")
        assert (data.job_id, data.status) == (1, "pending")

    @pytest.mark.parametrize("field", ["job_id", "status"])
    def test_missing_raises(self, field):
        with pytest.raises(ValidationError):
            SkillDraftJobResponse(**without(dict(job_id=1, status="x"), field))


class TestUsedPack:

    def test_defaults(self):
        data = UsedPack(slug="s", name="n")
        assert data.id is None
        assert data.domain_id is None
        assert data.chunks == 0

    def test_full(self):
        data = UsedPack(id=1, slug="s", name="n", domain_id=2, chunks=7)
        assert data.chunks == 7

    @pytest.mark.parametrize("field", ["slug", "name"])
    def test_missing_required_raises(self, field):
        with pytest.raises(ValidationError):
            UsedPack(**without(dict(slug="s", name="n"), field))


class TestSkillDraftResult:

    PAYLOAD = dict(skill_name="s", description="d", content="c", grounded=True)

    def test_defaults(self):
        data = SkillDraftResult(**self.PAYLOAD)
        assert data.sources == []
        assert data.used_packs == []
        assert data.warnings == []

    def test_builds_nested_used_packs(self):
        data = SkillDraftResult(
            **self.PAYLOAD, used_packs=[dict(slug="s", name="n", chunks=2)]
        )
        assert isinstance(data.used_packs[0], UsedPack)
        assert data.used_packs[0].chunks == 2

    @pytest.mark.parametrize("field", list(PAYLOAD))
    def test_missing_required_raises(self, field):
        with pytest.raises(ValidationError):
            SkillDraftResult(**without(self.PAYLOAD, field))

    def test_invalid_nested_used_pack_raises(self):
        with pytest.raises(ValidationError):
            SkillDraftResult(**self.PAYLOAD, used_packs=[{"slug": "only-slug"}])

    def test_json_round_trip(self):
        original = SkillDraftResult(**self.PAYLOAD, warnings=["w"], sources=["u"])
        assert SkillDraftResult.model_validate_json(original.model_dump_json()) == original


class TestSkillDraftStatus:

    def test_pending_has_no_draft_or_error(self):
        data = SkillDraftStatus(job_id=1, status="pending")
        assert data.error is None
        assert data.draft is None

    def test_done_with_draft_dict(self):
        data = SkillDraftStatus(
            job_id=1,
            status="done",
            draft=dict(skill_name="s", description="d", content="c", grounded=False),
        )
        assert isinstance(data.draft, SkillDraftResult)

    def test_failed_with_error(self):
        assert SkillDraftStatus(job_id=1, status="failed", error="boom").error == "boom"

    def test_invalid_draft_raises(self):
        with pytest.raises(ValidationError):
            SkillDraftStatus(job_id=1, status="done", draft={"skill_name": "s"})


class TestSkillDraftConfirm:

    def test_all_defaults(self):
        data = SkillDraftConfirm()
        assert data.skill_name is None
        assert data.description is None
        assert data.content is None
        assert data.domain_ids == []

    @pytest.mark.parametrize(
        "field,limit",
        [("skill_name", 100), ("description", 255), ("content", 50_000)],
    )
    def test_length_boundaries(self, field, limit):
        SkillDraftConfirm(**{field: "x" * limit})
        SkillDraftConfirm(**{field: "x"})
        with pytest.raises(ValidationError):
            SkillDraftConfirm(**{field: "x" * (limit + 1)})
        with pytest.raises(ValidationError):
            SkillDraftConfirm(**{field: ""})


class TestAttachPacks:

    def test_request_valid(self):
        assert AttachPacksRequest(config_bundle_id=1).config_bundle_id == 1

    def test_request_missing_raises(self):
        with pytest.raises(ValidationError):
            AttachPacksRequest()

    def test_response_valid(self):
        data = AttachPacksResponse(bundle_id=1, knowledge_pack_ids=[2, 3])
        assert data.knowledge_pack_ids == [2, 3]

    @pytest.mark.parametrize("field", ["bundle_id", "knowledge_pack_ids"])
    def test_response_missing_raises(self, field):
        with pytest.raises(ValidationError):
            AttachPacksResponse(**without(dict(bundle_id=1, knowledge_pack_ids=[]), field))

class TestMySkillCreate:

    PAYLOAD = dict(skill_name="s", description="d", content="c")

    def test_valid_defaults(self):
        assert MySkillCreate(**self.PAYLOAD).domain_ids == []

    @pytest.mark.parametrize("field", list(PAYLOAD))
    def test_missing_required_raises(self, field):
        with pytest.raises(ValidationError):
            MySkillCreate(**without(self.PAYLOAD, field))

    @pytest.mark.parametrize(
        "field,limit",
        [("skill_name", 100), ("description", 255), ("content", 50_000)],
    )
    def test_length_boundaries(self, field, limit):
        MySkillCreate(**{**self.PAYLOAD, field: "x" * limit})
        MySkillCreate(**{**self.PAYLOAD, field: "x"})
        with pytest.raises(ValidationError):
            MySkillCreate(**{**self.PAYLOAD, field: "x" * (limit + 1)})
        with pytest.raises(ValidationError):
            MySkillCreate(**{**self.PAYLOAD, field: ""})

    def test_domain_ids_not_shared_between_instances(self):
        a = MySkillCreate(**self.PAYLOAD)
        b = MySkillCreate(**self.PAYLOAD)
        a.domain_ids.append(1)
        assert b.domain_ids == []


class TestMySkillImport:

    def test_valid_minimal(self):
        data = MySkillImport(markdown="# hi")
        assert data.skill_name is None
        assert data.description is None
        assert data.domain_ids == []

    def test_missing_markdown_raises(self):
        with pytest.raises(ValidationError):
            MySkillImport()

    def test_empty_markdown_raises(self):
        with pytest.raises(ValidationError):
            MySkillImport(markdown="")

    def test_markdown_max_length(self):
        MySkillImport(markdown="x" * 60_000)
        with pytest.raises(ValidationError):
            MySkillImport(markdown="x" * 60_001)

    @pytest.mark.parametrize("field,limit", [("skill_name", 100), ("description", 255)])
    def test_optional_overrides_max_length(self, field, limit):
        MySkillImport(markdown="m", **{field: "x" * limit})
        with pytest.raises(ValidationError):
            MySkillImport(markdown="m", **{field: "x" * (limit + 1)})


class TestMySkillUpdate:

    def test_all_none_by_default(self):
        data = MySkillUpdate()
        assert data.model_dump() == dict(skill_name=None, description=None, content=None)

    def test_exclude_unset_only_returns_sent_fields(self):
        data = MySkillUpdate(description="new")
        assert data.model_dump(exclude_unset=True) == {"description": "new"}

    @pytest.mark.parametrize(
        "field,limit",
        [("skill_name", 100), ("description", 255), ("content", 50_000)],
    )
    def test_length_boundaries(self, field, limit):
        MySkillUpdate(**{field: "x" * limit})
        with pytest.raises(ValidationError):
            MySkillUpdate(**{field: "x" * (limit + 1)})
        with pytest.raises(ValidationError):
            MySkillUpdate(**{field: ""})


class TestMySkillSummaryAndRead:

    def _orm(self, **overrides):
        base = dict(
            id=1, skill_name="s", description="d", content_hash=VALID_HASH,
            visibility=SkillVisibility.PRIVATE, archived_at=None,
            content="body", created_at=NOW, updated_at=NOW,
        )
        base.update(overrides)
        return orm_mock(**base)

    def test_summary_from_orm(self):
        data = MySkillSummary.model_validate(self._orm())
        assert data.visibility == SkillVisibility.PRIVATE
        assert data.archived_at is None

    def test_summary_archived(self):
        assert MySkillSummary.model_validate(self._orm(archived_at=NOW)).archived_at == NOW

    def test_summary_invalid_visibility_raises(self):
        with pytest.raises(ValidationError):
            MySkillSummary.model_validate(self._orm(visibility="secret"))

    def test_summary_does_not_expose_content(self):
        assert "content" not in MySkillSummary.model_fields

    def test_read_extends_summary(self):
        assert issubclass(MySkillRead, MySkillSummary)

    def test_read_from_orm(self):
        data = MySkillRead.model_validate(self._orm())
        assert data.content == "body"
        assert data.created_at == NOW
        assert data.updated_at == NOW

    def test_read_missing_content_raises(self):
        orm = self._orm()
        del orm.content  # MagicMock would auto-create it otherwise
        with pytest.raises(ValidationError):
            MySkillRead.model_validate(orm)

class TestMyToolCreate:

    PAYLOAD = dict(tool_name="t", description="d", url="https://example.com")

    def test_valid_defaults(self):
        data = MyToolCreate(**self.PAYLOAD)
        assert data.auth_type == ToolAuthType.NONE
        assert data.auth_description is None
        assert data.domain_ids == []

    @pytest.mark.parametrize("field", list(PAYLOAD))
    def test_missing_required_raises(self, field):
        with pytest.raises(ValidationError):
            MyToolCreate(**without(self.PAYLOAD, field))

    @pytest.mark.parametrize(
        "field,limit",
        [("tool_name", 100), ("description", 255), ("url", 2048)],
    )
    def test_length_boundaries(self, field, limit):
        MyToolCreate(**{**self.PAYLOAD, field: "x" * limit})
        with pytest.raises(ValidationError):
            MyToolCreate(**{**self.PAYLOAD, field: "x" * (limit + 1)})
        with pytest.raises(ValidationError):
            MyToolCreate(**{**self.PAYLOAD, field: ""})

    def test_auth_description_max_255(self):
        MyToolCreate(**self.PAYLOAD, auth_description="x" * 255)
        with pytest.raises(ValidationError):
            MyToolCreate(**self.PAYLOAD, auth_description="x" * 256)

    @pytest.mark.parametrize("auth_type", list(ToolAuthType))
    def test_accepts_every_auth_type(self, auth_type):
        assert MyToolCreate(**self.PAYLOAD, auth_type=auth_type).auth_type == auth_type

    def test_invalid_auth_type_raises(self):
        with pytest.raises(ValidationError):
            MyToolCreate(**self.PAYLOAD, auth_type="magic")


class TestMyToolUpdate:

    def test_all_none_by_default(self):
        assert MyToolUpdate().model_dump(exclude_unset=True) == {}

    def test_tool_name_is_not_updatable(self):
        assert "tool_name" not in MyToolUpdate.model_fields

    @pytest.mark.parametrize("field,limit", [("description", 255), ("url", 2048)])
    def test_length_boundaries(self, field, limit):
        MyToolUpdate(**{field: "x" * limit})
        with pytest.raises(ValidationError):
            MyToolUpdate(**{field: "x" * (limit + 1)})
        with pytest.raises(ValidationError):
            MyToolUpdate(**{field: ""})

    def test_auth_description_may_be_empty_string(self):
        """No min_length on auth_description in update schema."""
        assert MyToolUpdate(auth_description="").auth_description == ""

    def test_invalid_auth_type_raises(self):
        with pytest.raises(ValidationError):
            MyToolUpdate(auth_type="magic")


class TestMyToolReadAndResponse:

    def _orm(self, **overrides):
        base = dict(
            id=1, tool_name="t", description="d", url="https://e.com",
            auth_type=ToolAuthType.NONE, auth_description=None,
            archived_at=None, created_at=NOW, updated_at=NOW,
        )
        base.update(overrides)
        return orm_mock(**base)

    def test_from_orm(self):
        data = MyToolRead.model_validate(self._orm())
        assert data.auth_type == ToolAuthType.NONE
        assert data.archived_at is None

    def test_response_with_default_warnings(self):
        data = MyToolResponse(tool=MyToolRead.model_validate(self._orm()))
        assert data.warnings == []

    def test_response_builds_tool_from_dict(self):
        data = MyToolResponse(
            tool=dict(
                id=1, tool_name="t", description="d", url="u",
                auth_type=ToolAuthType.NONE, created_at=NOW, updated_at=NOW,
            ),
            warnings=["url is not https"],
        )
        assert isinstance(data.tool, MyToolRead)
        assert data.warnings == ["url is not https"]

    def test_response_missing_tool_raises(self):
        with pytest.raises(ValidationError):
            MyToolResponse()


class TestAdminSkills:

    def _orm(self, **overrides):
        base = dict(
            id=1, skill_name="s", description="d", archived_at=None,
            updated_at=NOW, content="body", owner_id=None,
        )
        base.update(overrides)
        return orm_mock(**base)

    def test_list_item_from_orm(self):
        data = AdminSkillListItem.model_validate(self._orm())
        assert data.archived_at is None

    def test_list_item_archived_at_defaults_to_none(self):
        data = AdminSkillListItem(id=1, skill_name="s", description="d", updated_at=NOW)
        assert data.archived_at is None

    def test_list_item_missing_updated_at_raises(self):
        with pytest.raises(ValidationError):
            AdminSkillListItem(id=1, skill_name="s", description="d")

    def test_read_from_orm_with_owner(self):
        data = AdminSkillRead.model_validate(self._orm(owner_id=9))
        assert data.content == "body"
        assert data.owner_id == 9

    def test_read_global_skill_has_no_owner(self):
        assert AdminSkillRead.model_validate(self._orm()).owner_id is None

    def test_archive_for_violation_valid(self):
        assert ArchiveForViolation(reason="spam").reason == "spam"

    def test_archive_for_violation_reason_bounds(self):
        ArchiveForViolation(reason="x" * 255)
        with pytest.raises(ValidationError):
            ArchiveForViolation(reason="x" * 256)
        with pytest.raises(ValidationError):
            ArchiveForViolation(reason="")

    def test_archive_for_violation_missing_raises(self):
        with pytest.raises(ValidationError):
            ArchiveForViolation()

    def test_access_log_entry_from_orm(self):
        obj = orm_mock(
            id=1, admin_id=2, skill_id=3, action="view", note=None, created_at=NOW
        )
        data = AccessLogEntry.model_validate(obj)
        assert data.action == "view"
        assert data.note is None

    def test_access_log_entry_nullable_ids(self):
        data = AccessLogEntry(
            id=1, admin_id=None, skill_id=None, action="a", created_at=NOW
        )
        assert data.admin_id is None
        assert data.skill_id is None

    def test_access_log_entry_missing_action_raises(self):
        with pytest.raises(ValidationError):
            AccessLogEntry(id=1, admin_id=1, skill_id=1, created_at=NOW)

    def test_admin_tool_item_valid(self):
        data = AdminToolItem(
            id=1, tool_name="t", description="d", url_masked="https://***"
        )
        assert data.archived_at is None
        assert data.url_masked == "https://***"

    def test_admin_tool_item_has_no_raw_url_field(self):
        assert "url" not in AdminToolItem.model_fields

    def test_admin_tool_item_ignores_raw_url_in_payload(self):
        data = AdminToolItem(
            id=1, tool_name="t", description="d", url_masked="m",
            url="https://secret.example.com",
        )
        assert "url" not in data.model_dump()

    def test_user_overview_valid(self):
        data = UserOverview(
            user_id=1, private_skills=2, private_tools=3, bundles=4,
            token_events=5, tokens_used=6, token_limit=7,
        )
        assert data.bundles == 4

    @pytest.mark.parametrize("field", list(UserOverview.model_fields))
    def test_user_overview_missing_field_raises(self, field):
        payload = {name: 1 for name in UserOverview.model_fields}
        with pytest.raises(ValidationError):
            UserOverview(**without(payload, field))

class TestCustomAgentCreate:

    def test_valid_defaults(self):
        data = CustomAgentCreate(name="n")
        assert data.description == ""
        assert data.skill_ids == []
        assert data.tool_ids == []
        assert data.knowledge_pack_ids == []

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            CustomAgentCreate()

    def test_name_bounds(self):
        CustomAgentCreate(name="x" * 100)
        with pytest.raises(ValidationError):
            CustomAgentCreate(name="x" * 101)
        with pytest.raises(ValidationError):
            CustomAgentCreate(name="")

    def test_description_max_255(self):
        CustomAgentCreate(name="n", description="x" * 255)
        with pytest.raises(ValidationError):
            CustomAgentCreate(name="n", description="x" * 256)

    def test_default_lists_not_shared(self):
        a = CustomAgentCreate(name="a")
        b = CustomAgentCreate(name="b")
        a.skill_ids.append(1)
        assert b.skill_ids == []

    def test_non_int_ids_raise(self):
        with pytest.raises(ValidationError):
            CustomAgentCreate(name="n", tool_ids=["x"])


class TestCustomAgentRead:

    def test_from_orm_with_refs(self):
        obj = orm_mock(
            id=1, name="n", description="d", agent_id=2,
            skills=[orm_mock(id=10, skill_name="ignored")],
            tools=[orm_mock(id=20)],
            knowledge_packs=[orm_mock(id=30), orm_mock(id=31)],
        )
        data = CustomAgentRead.model_validate(obj)
        assert [s.id for s in data.skills] == [10]
        assert [t.id for t in data.tools] == [20]
        assert [p.id for p in data.knowledge_packs] == [30, 31]

    def test_refs_expose_only_id(self):
        obj = orm_mock(
            id=1, name="n", description="d", agent_id=2,
            skills=[orm_mock(id=10, skill_name="x")], tools=[], knowledge_packs=[],
        )
        assert CustomAgentRead.model_validate(obj).skills[0].model_dump() == {"id": 10}

    def test_empty_collections(self):
        obj = orm_mock(
            id=1, name="n", description="d", agent_id=2,
            skills=[], tools=[], knowledge_packs=[],
        )
        data = CustomAgentRead.model_validate(obj)
        assert data.skills == data.tools == data.knowledge_packs == []

    def test_missing_agent_id_raises(self):
        with pytest.raises(ValidationError):
            CustomAgentRead(
                id=1, name="n", description="d",
                skills=[], tools=[], knowledge_packs=[],
            )

class TestConfigBundleUpdate:

    def test_all_none_by_default(self):
        assert ConfigBundleUpdate().model_dump(exclude_unset=True) == {}

    def test_name_bounds(self):
        ConfigBundleUpdate(name="x" * 100)
        with pytest.raises(ValidationError):
            ConfigBundleUpdate(name="x" * 101)
        with pytest.raises(ValidationError):
            ConfigBundleUpdate(name="")

    def test_description_may_be_empty_but_max_255(self):
        assert ConfigBundleUpdate(description="").description == ""
        ConfigBundleUpdate(description="x" * 255)
        with pytest.raises(ValidationError):
            ConfigBundleUpdate(description="x" * 256)


class TestBundleItems:

    def test_defaults(self):
        data = BundleItems()
        assert data.skill_ids == []
        assert data.tool_ids == []
        assert data.knowledge_pack_ids == []

    def test_values(self):
        data = BundleItems(skill_ids=[1], tool_ids=[2], knowledge_pack_ids=[3])
        assert (data.skill_ids, data.tool_ids, data.knowledge_pack_ids) == ([1], [2], [3])

    def test_default_lists_not_shared(self):
        a, b = BundleItems(), BundleItems()
        a.skill_ids.append(1)
        assert b.skill_ids == []


class TestEffectiveReads:

    def test_skill_from_orm(self):
        obj = orm_mock(id=1, name="s", content_hash=VALID_HASH, archived=False)
        data = EffectiveSkillRead.model_validate(obj)
        assert data.archived is False

    def test_tool_from_orm(self):
        obj = orm_mock(id=1, name="t", url="u", auth_type="none", archived=True)
        data = EffectiveToolRead.model_validate(obj)
        assert data.archived is True
        assert data.auth_type == "none"

    def test_pack_from_orm(self):
        obj = orm_mock(id=1, slug="s", version=4, archived=False)
        assert EffectivePackRead.model_validate(obj).version == 4

    @pytest.mark.parametrize(
        "schema,payload",
        [
            (EffectiveSkillRead, dict(id=1, name="s", content_hash="h", archived=False)),
            (EffectiveToolRead, dict(id=1, name="t", url="u", auth_type="a", archived=False)),
            (EffectivePackRead, dict(id=1, slug="s", version=1, archived=False)),
        ],
    )
    def test_archived_is_required(self, schema, payload):
        with pytest.raises(ValidationError):
            schema(**without(payload, "archived"))

    def test_effective_bundle_from_orm(self):
        obj = orm_mock(
            bundle_id=1, agent_id=2, agent_name="agent",
            skills=[orm_mock(id=1, name="s", content_hash="h", archived=False)],
            tools=[orm_mock(id=2, name="t", url="u", auth_type="none", archived=False)],
            packs=[orm_mock(id=3, slug="p", version=1, archived=True)],
            version_hash="v" * 8,
        )
        data = EffectiveBundleRead.model_validate(obj)
        assert data.skills[0].name == "s"
        assert data.tools[0].url == "u"
        assert data.packs[0].archived is True
        assert data.version_hash == "v" * 8

    def test_effective_bundle_missing_version_hash_raises(self):
        with pytest.raises(ValidationError):
            EffectiveBundleRead(
                bundle_id=1, agent_id=2, agent_name="a",
                skills=[], tools=[], packs=[],
            )

    def test_effective_bundle_invalid_nested_raises(self):
        with pytest.raises(ValidationError):
            EffectiveBundleRead(
                bundle_id=1, agent_id=2, agent_name="a",
                skills=[{"id": 1}], tools=[], packs=[], version_hash="h",
            )
class TestHintRequest:

    def test_valid(self):
        assert HintRequest(intent="build an API").intent == "build an API"

    def test_value_is_stripped(self):
        assert HintRequest(intent="  hello \n").intent == "hello"

    @pytest.mark.parametrize("blank", ["", " ", "   ", "\n\t "])
    def test_blank_raises(self, blank):
        with pytest.raises(ValidationError):
            HintRequest(intent=blank)

    def test_blank_error_message_for_whitespace(self):
        with pytest.raises(ValidationError, match="intent cannot be blank"):
            HintRequest(intent="   ")

    def test_max_length_boundary(self):
        assert len(HintRequest(intent="x" * 1000).intent) == 1000
        with pytest.raises(ValidationError):
            HintRequest(intent="x" * 1001)

    def test_missing_raises(self):
        with pytest.raises(ValidationError):
            HintRequest()


class TestHintModels:

    def test_hint_ref(self):
        assert HintRef(id=1, name="n").name == "n"

    def test_hint_item_description_optional(self):
        assert HintItem(id=1, name="n").description is None

    def test_hint_item_extends_ref(self):
        assert issubclass(HintItem, HintRef)

    def test_hint_profile_defaults(self):
        data = HintProfile(id=1, name="n")
        assert data.base_skills == []
        assert data.base_tools == []

    def test_hint_profile_nested_refs(self):
        data = HintProfile(
            id=1, name="n",
            base_skills=[{"id": 1, "name": "s"}],
            base_tools=[{"id": 2, "name": "t"}],
        )
        assert isinstance(data.base_skills[0], HintRef)

    def test_hint_response_defaults(self):
        data = HintResponse()
        assert data.agent_profile is None
        assert data.skills == []
        assert data.tools == []
        assert data.knowledge_packs == []
        assert data.reasoning == ""

    def test_hint_response_builds_nested_models(self):
        data = HintResponse(
            agent_profile={"id": 1, "name": "agent"},
            skills=[{"id": 2, "name": "s", "description": "d"}],
            tools=[{"id": 3, "name": "t"}],
            knowledge_packs=[{"id": 4, "name": "p"}],
            reasoning="because",
        )
        assert isinstance(data.agent_profile, HintProfile)
        assert data.skills[0].description == "d"
        assert data.reasoning == "because"

    def test_hint_response_invalid_nested_raises(self):
        with pytest.raises(ValidationError):
            HintResponse(skills=[{"id": 1}])

class TestSkillUpdate:

    def test_defaults(self):
        assert SkillUpdate().model_dump(exclude_unset=True) == {}

    def test_description_may_be_empty_max_255(self):
        assert SkillUpdate(description="").description == ""
        SkillUpdate(description="x" * 255)
        with pytest.raises(ValidationError):
            SkillUpdate(description="x" * 256)

    def test_content_bounds(self):
        SkillUpdate(content="x" * 50_000)
        with pytest.raises(ValidationError):
            SkillUpdate(content="x" * 50_001)
        with pytest.raises(ValidationError):
            SkillUpdate(content="")


class TestToolUpdate:

    def test_defaults(self):
        assert ToolUpdate().model_dump(exclude_unset=True) == {}

    def test_url_max_2048(self):
        ToolUpdate(url="x" * 2048)
        with pytest.raises(ValidationError):
            ToolUpdate(url="x" * 2049)

    def test_description_and_auth_description_max_255(self):
        for field in ("description", "auth_description"):
            ToolUpdate(**{field: "x" * 255})
            with pytest.raises(ValidationError):
                ToolUpdate(**{field: "x" * 256})

    @pytest.mark.parametrize("auth_type", list(ToolAuthType))
    def test_accepts_every_auth_type(self, auth_type):
        assert ToolUpdate(auth_type=auth_type).auth_type == auth_type

    def test_invalid_auth_type_raises(self):
        with pytest.raises(ValidationError):
            ToolUpdate(auth_type="magic")


class TestAgentUpdate:

    def test_defaults_are_none_not_empty(self):
        data = AgentUpdate()
        assert data.skill_ids is None
        assert data.tool_ids is None

    def test_empty_list_differs_from_unset(self):
        """[] means 'clear all', None means 'leave unchanged'."""
        data = AgentUpdate(skill_ids=[])
        assert data.skill_ids == []
        assert data.model_dump(exclude_unset=True) == {"skill_ids": []}

    def test_description_max_255(self):
        AgentUpdate(description="x" * 255)
        with pytest.raises(ValidationError):
            AgentUpdate(description="x" * 256)

    def test_non_int_ids_raise(self):
        with pytest.raises(ValidationError):
            AgentUpdate(tool_ids=["a"])

class TestConfigBundleClone:

    def test_valid_minimal(self):
        data = ConfigBundleClone(name="copy")
        assert data.description is None

    def test_with_description(self):
        assert ConfigBundleClone(name="c", description="d").description == "d"

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            ConfigBundleClone(description="d")

class TestJobCreatedResponse:

    def test_valid(self):
        data = JobCreatedResponse(job_id=1, status="pending")
        assert data.job_id == 1

    @pytest.mark.parametrize("field", ["job_id", "status"])
    def test_missing_raises(self, field):
        with pytest.raises(ValidationError):
            JobCreatedResponse(**without(dict(job_id=1, status="s"), field))


class TestJobStatusResponse:

    def _orm(self, **overrides):
        base = dict(
            id=1, job_type="ingest_web", status="pending", result=None,
            error=None, created_at=NOW, started_at=None, finished_at=None,
        )
        base.update(overrides)
        return orm_mock(**base)

    def test_from_orm_pending(self):
        data = JobStatusResponse.model_validate(self._orm())
        assert data.result is None
        assert data.error is None
        assert data.started_at is None
        assert data.finished_at is None

    def test_from_orm_finished_with_result(self):
        data = JobStatusResponse.model_validate(
            self._orm(
                status="done", result={"documents": 3},
                started_at=NOW, finished_at=NOW,
            )
        )
        assert data.result == {"documents": 3}
        assert data.finished_at == NOW

    def test_from_orm_failed_with_error(self):
        assert JobStatusResponse.model_validate(self._orm(status="failed", error="x")).error == "x"

    def test_optional_fields_have_defaults_when_built_directly(self):
        data = JobStatusResponse(
            id=1, job_type="t", status="s", created_at=NOW
        )
        assert data.result is None
        assert data.started_at is None

    @pytest.mark.parametrize("field", ["id", "job_type", "status", "created_at"])
    def test_missing_required_raises(self, field):
        payload = dict(id=1, job_type="t", status="s", created_at=NOW)
        with pytest.raises(ValidationError):
            JobStatusResponse(**without(payload, field))

    def test_non_dict_result_raises(self):
        with pytest.raises(ValidationError):
            JobStatusResponse(
                id=1, job_type="t", status="s", created_at=NOW, result="oops"
            )

class TestAdminUserRead:

    def test_from_orm(self):
        obj = orm_mock(
            id=1, username="a", email="a@example.com", role=UserRole.USER,
            tokens_used=1, token_limit=10, created_at=NOW,
        )
        data = AdminUserRead.model_validate(obj)
        assert data.created_at == NOW
        assert data.role == UserRole.USER

    def test_missing_created_at_raises(self):
        with pytest.raises(ValidationError):
            AdminUserRead(
                id=1, username="a", email="a@example.com", role=UserRole.USER,
                tokens_used=1, token_limit=10,
            )


class TestRoleUpdate:

    @pytest.mark.parametrize("role", [UserRole.USER, UserRole.ADMIN])
    def test_accepts_user_and_admin(self, role):
        assert RoleUpdate(role=role).role == role

    @pytest.mark.parametrize("role", [UserRole.USER, UserRole.ADMIN])
    def test_accepts_enum_values(self, role):
        assert RoleUpdate(role=role.value).role == role

    @pytest.mark.parametrize(
        "role", [r for r in UserRole if r not in (UserRole.USER, UserRole.ADMIN)]
    )
    def test_rejects_any_other_role(self, role):
        with pytest.raises(ValidationError):
            RoleUpdate(role=role)

    def test_rejects_unknown_role(self):
        with pytest.raises(ValidationError):
            RoleUpdate(role="superuser")

    def test_missing_raises(self):
        with pytest.raises(ValidationError):
            RoleUpdate()


class TestTokenLimitUpdate:

    @pytest.mark.parametrize("value", [0, 1, 1_000_000])
    def test_valid(self, value):
        assert TokenLimitUpdate(token_limit=value).token_limit == value

    def test_negative_raises(self):
        with pytest.raises(ValidationError):
            TokenLimitUpdate(token_limit=-1)

    def test_missing_raises(self):
        with pytest.raises(ValidationError):
            TokenLimitUpdate()

    def test_non_int_raises(self):
        with pytest.raises(ValidationError):
            TokenLimitUpdate(token_limit="lots")

class TestDeviceTokenCreate:

    @pytest.mark.parametrize(
        "scope",
        ["read", "read write", "skills:read tools:write", "a.b-c_d", "x" * 100, "a b c d e", "0"],
    )
    def test_valid_scopes(self, scope):
        assert DeviceTokenCreate(scope=scope).scope == scope

    @pytest.mark.parametrize(
        "scope",
        [
            "",
            " ",
            "Read",
            "read  write",
            " read",
            "read ",
            "read,write",
            "read\twrite",
            "read/write",
            "scope!",
            "x" * 101,
        ],
    )
    def test_invalid_scopes(self, scope):
        with pytest.raises(ValidationError):
            DeviceTokenCreate(scope=scope)

    def test_missing_scope_raises(self):
        with pytest.raises(ValidationError):
            DeviceTokenCreate()

    def test_defaults(self):
        data = DeviceTokenCreate(scope="read")
        assert data.name == "device"
        assert data.config_bundle_id is None

    @pytest.mark.parametrize("name", ["", "x" * 101])
    def test_invalid_name_raises(self, name):
        with pytest.raises(ValidationError):
            DeviceTokenCreate(scope="read", name=name)

    def test_user_id_is_not_part_of_the_schema(self):
        assert set(DeviceTokenCreate.model_fields) == {"scope", "name", "config_bundle_id"}