from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.schemas.agent import AgentCreate, AgentRead, SkillRead as AgentSkillRead, ToolRead as AgentToolRead
from src.schemas.config_bundle import ConfigBundleCreate, ConfigBundleFromAgent, ConfigBundleRead
from src.schemas.device import DeviceCodeInitiate, DeviceCodeRead, DeviceVerify, DeviceTokenResponse
from src.schemas.document import DocumentCreate, DocumentRead
from src.schemas.domain import DomainCreate, DomainRead
from src.schemas.knowledge import IngestFileRequest, IngestWebRequest, SearchRequest, SearchResultResponse
from src.schemas.knowledge_pack import KnowledgePackCreate, KnowledgePackRead
from src.schemas.skill import SkillCreate, SkillRead
from src.schemas.tool import ToolCreate, ToolRead
from src.schemas.user import UserCreate, UserUpdate, ChangePassword, UserRead

from src.db.enums.document_status import DocumentStatus
from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType


NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)
VALID_HASH = "a" * 64


def orm_mock(**kwargs) -> MagicMock:
    """Return a MagicMock whose attributes match kwargs — simulates an ORM row."""
    obj = MagicMock()
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


class TestAgentCreate:

    def test_valid(self):
        data = AgentCreate(name="coder", description="coding agent", skill_ids=[1], tool_ids=[2])
        assert data.name == "coder"
        assert data.skill_ids == [1]

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            AgentCreate(description="x", skill_ids=[], tool_ids=[])

    def test_missing_description_raises(self):
        with pytest.raises(ValidationError):
            AgentCreate(name="x", skill_ids=[], tool_ids=[])

    def test_empty_skill_and_tool_ids_are_valid(self):
        data = AgentCreate(name="x", description="y", skill_ids=[], tool_ids=[])
        assert data.skill_ids == []
        assert data.tool_ids == []


class TestAgentSkillRead:

    def test_from_orm(self):
        obj = orm_mock(id=1, skill_name="summarization", description="Summarize text")
        data = AgentSkillRead.model_validate(obj)
        assert data.id == 1
        assert data.skill_name == "summarization"

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            AgentSkillRead(skill_name="x", description="y")


class TestAgentToolRead:

    def test_from_orm(self):
        obj = orm_mock(id=2, tool_name="web_search", description="Search")
        data = AgentToolRead.model_validate(obj)
        assert data.id == 2
        assert data.tool_name == "web_search"


class TestAgentRead:

    def test_from_orm_with_nested_lists(self):
        skill_obj = orm_mock(id=1, skill_name="summarization", description="desc")
        tool_obj = orm_mock(id=2, tool_name="web_search", description="desc")
        agent_obj = orm_mock(
            id=10, agent_name="coder", description="coding", skills=[skill_obj], tools=[tool_obj]
        )
        data = AgentRead.model_validate(agent_obj)
        assert data.id == 10
        assert len(data.skills) == 1
        assert data.skills[0].skill_name == "summarization"
        assert len(data.tools) == 1

    def test_empty_skills_and_tools_allowed(self):
        obj = orm_mock(id=1, agent_name="x", description="y", skills=[], tools=[])
        data = AgentRead.model_validate(obj)
        assert data.skills == []
        assert data.tools == []


class TestConfigBundleCreate:

    def test_valid_with_knowledge_packs(self):
        data = ConfigBundleCreate(
            agent_id=1, name="bundle", description="desc",
            skill_ids=[1], tool_ids=[2], knowledge_pack_ids=[3],
        )
        assert data.knowledge_pack_ids == [3]

    def test_knowledge_pack_ids_defaults_to_empty_list(self):
        data = ConfigBundleCreate(
            agent_id=1, name="b", description="d", skill_ids=[], tool_ids=[]
        )
        assert data.knowledge_pack_ids == []

    def test_missing_agent_id_raises(self):
        with pytest.raises(ValidationError):
            ConfigBundleCreate(name="b", description="d", skill_ids=[], tool_ids=[])


class TestConfigBundleFromAgent:

    def test_valid(self):
        data = ConfigBundleFromAgent(agent_id=5, name="bundle", description="from agent")
        assert data.agent_id == 5

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            ConfigBundleFromAgent(agent_id=1, description="d")


class TestConfigBundleRead:

    def test_from_orm(self):
        pack_obj = orm_mock(id=1, name="pack", slug="pack-slug", domain_id=1, description="d", version=1)
        skill_obj = orm_mock(id=1, skill_name="s", description="d")
        tool_obj = orm_mock(id=1, tool_name="t", description="d")
        bundle_obj = orm_mock(
            id=7, user_id=3, agent_id=2, name="bundle", description="desc",
            skills=[skill_obj], tools=[tool_obj], knowledge_packs=[pack_obj],
        )
        data = ConfigBundleRead.model_validate(bundle_obj)
        assert data.id == 7
        assert len(data.knowledge_packs) == 1
        assert data.knowledge_packs[0].slug == "pack-slug"


class TestDeviceCodeInitiate:

    def test_valid(self):
        data = DeviceCodeInitiate(user_id=1, scope="read write")
        assert data.scope == "read write"

    def test_missing_user_id_raises(self):
        with pytest.raises(ValidationError):
            DeviceCodeInitiate(scope="read")


class TestDeviceCodeRead:

    def test_from_orm(self):
        obj = orm_mock(
            id=1, device_code="ABCD-1234", scope="read",
            expires_at=NOW, interval=5,
        )
        data = DeviceCodeRead.model_validate(obj)
        assert data.device_code == "ABCD-1234"
        assert data.interval == 5


class TestDeviceVerify:

    def test_valid(self):
        data = DeviceVerify(device_code="ABCD-1234")
        assert data.device_code == "ABCD-1234"

    def test_missing_device_code_raises(self):
        with pytest.raises(ValidationError):
            DeviceVerify()


class TestDeviceTokenResponse:

    def test_valid(self):
        data = DeviceTokenResponse(access_token="tok123")
        assert data.token_type == "bearer"
        assert data.access_token == "tok123"

    def test_token_type_default_is_bearer(self):
        data = DeviceTokenResponse(access_token="x")
        assert data.token_type == "bearer"

    def test_missing_access_token_raises(self):
        with pytest.raises(ValidationError):
            DeviceTokenResponse()


class TestDocumentCreate:

    def _valid_payload(self, **overrides):
        base = dict(
            source="https://example.com/doc.pdf",
            document_type=DocumentType.BOOK,
            knowledge_type=KnowledgeType.REFERENCE,
            size=1024,
            content_hash=VALID_HASH,
            scraped_at=NOW,
            embedding_model="BAAI/bge-m3",
        )
        base.update(overrides)
        return base

    def test_valid_minimal(self):
        data = DocumentCreate(**self._valid_payload())
        assert data.embedding_version is None
        assert data.knowledge_pack_id is None

    def test_content_hash_too_short_raises(self):
        with pytest.raises(ValidationError):
            DocumentCreate(**self._valid_payload(content_hash="a" * 63))

    def test_content_hash_too_long_raises(self):
        with pytest.raises(ValidationError):
            DocumentCreate(**self._valid_payload(content_hash="a" * 65))

    def test_content_hash_exact_64_chars_is_valid(self):
        data = DocumentCreate(**self._valid_payload(content_hash="b" * 64))
        assert len(data.content_hash) == 64

    def test_invalid_document_type_raises(self):
        with pytest.raises(ValidationError):
            DocumentCreate(**self._valid_payload(document_type="INVALID_TYPE"))

    def test_invalid_knowledge_type_raises(self):
        with pytest.raises(ValidationError):
            DocumentCreate(**self._valid_payload(knowledge_type="INVALID_KIND"))

    def test_optional_fields_accepted(self):
        data = DocumentCreate(
            **self._valid_payload(embedding_version="v2", knowledge_pack_id=5)
        )
        assert data.embedding_version == "v2"
        assert data.knowledge_pack_id == 5

    def test_missing_source_raises(self):
        payload = self._valid_payload()
        del payload["source"]
        with pytest.raises(ValidationError):
            DocumentCreate(**payload)

    def test_missing_embedding_model_raises(self):
        payload = self._valid_payload()
        del payload["embedding_model"]
        with pytest.raises(ValidationError):
            DocumentCreate(**payload)


class TestDocumentRead:

    def test_from_orm(self):
        obj = orm_mock(
            id=1,
            source="https://example.com/doc.pdf",
            document_type=DocumentType.BOOK,
            knowledge_type=KnowledgeType.REFERENCE,
            size=1024,
            content_hash=VALID_HASH,
            version=1,
            scraped_at=NOW,
            created_at=NOW,
            status=DocumentStatus.INDEXED,
            embedding_model="BAAI/bge-m3",
            embedding_version=None,
            knowledge_pack_id=None,
        )
        data = DocumentRead.model_validate(obj)
        assert data.id == 1
        assert data.status == DocumentStatus.INDEXED
        assert data.embedding_version is None


class TestDomainCreate:

    def test_valid_root_domain(self):
        data = DomainCreate(slug="backend", name="Backend", description="Backend stuff")
        assert data.parent_domain_id is None

    def test_valid_child_domain(self):
        data = DomainCreate(slug="rest", name="REST", description="REST APIs", parent_domain_id=1)
        assert data.parent_domain_id == 1

    def test_missing_slug_raises(self):
        with pytest.raises(ValidationError):
            DomainCreate(name="x", description="y")

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            DomainCreate(slug="x", description="y")

    def test_missing_description_raises(self):
        with pytest.raises(ValidationError):
            DomainCreate(slug="x", name="y")


class TestDomainRead:

    def test_from_orm_leaf_domain(self):
        obj = orm_mock(
            id=1, slug="backend", name="Backend", description="desc",
            parent_domain_id=None, children=[],
        )
        data = DomainRead.model_validate(obj)
        assert data.id == 1
        assert data.children == []

    def test_from_orm_with_nested_children(self):
        child_obj = orm_mock(
            id=2, slug="rest", name="REST", description="REST APIs",
            parent_domain_id=1, children=[],
        )
        parent_obj = orm_mock(
            id=1, slug="backend", name="Backend", description="Backend",
            parent_domain_id=None, children=[child_obj],
        )
        data = DomainRead.model_validate(parent_obj)
        assert len(data.children) == 1
        assert data.children[0].slug == "rest"
        assert data.children[0].parent_domain_id == 1

    def test_children_defaults_to_empty_list(self):
        obj = orm_mock(
            id=1, slug="x", name="x", description="x",
            parent_domain_id=None, children=[],
        )
        data = DomainRead.model_validate(obj)
        assert data.children == []

    def test_deeply_nested_children(self):
        grandchild = orm_mock(id=3, slug="g", name="G", description="g", parent_domain_id=2, children=[])
        child = orm_mock(id=2, slug="c", name="C", description="c", parent_domain_id=1, children=[grandchild])
        parent = orm_mock(id=1, slug="p", name="P", description="p", parent_domain_id=None, children=[child])

        data = DomainRead.model_validate(parent)
        assert data.children[0].children[0].slug == "g"


class TestIngestFileRequest:

    def test_valid(self):
        data = IngestFileRequest(
            source="https://example.com/doc.pdf",
            document_type=DocumentType.BOOK,
            knowledge_type=KnowledgeType.REFERENCE,
            knowledge_pack_id=1,
        )
        assert data.knowledge_pack_id == 1

    def test_missing_source_raises(self):
        with pytest.raises(ValidationError):
            IngestFileRequest(
                document_type=DocumentType.BOOK,
                knowledge_type=KnowledgeType.REFERENCE,
                knowledge_pack_id=1,
            )

    def test_invalid_document_type_raises(self):
        with pytest.raises(ValidationError):
            IngestFileRequest(
                source="https://x.com", document_type="NOPE",
                knowledge_type=KnowledgeType.REFERENCE, knowledge_pack_id=1,
            )


class TestIngestWebRequest:

    def test_valid_with_defaults(self):
        data = IngestWebRequest(
            query="fastapi best practices",
            document_type=DocumentType.BLOG_POST,
            knowledge_type=KnowledgeType.EXAMPLE,
            knowledge_pack_id=2,
        )
        assert data.limit == 5

    def test_custom_limit(self):
        data = IngestWebRequest(
            query="q", limit=10,
            document_type=DocumentType.BLOG_POST,
            knowledge_type=KnowledgeType.EXAMPLE,
            knowledge_pack_id=2,
        )
        assert data.limit == 10

    def test_missing_query_raises(self):
        with pytest.raises(ValidationError):
            IngestWebRequest(
                document_type=DocumentType.BLOG_POST,
                knowledge_type=KnowledgeType.EXAMPLE,
                knowledge_pack_id=1,
            )


class TestSearchRequest:

    def test_valid_with_defaults(self):
        data = SearchRequest(query="hexagonal architecture", config_bundle_id=3)
        assert data.limit == 20
        assert data.top_n == 5
        assert data.k == 60

    def test_custom_values(self):
        data = SearchRequest(query="q", limit=10, top_n=3, k=30, config_bundle_id=1)
        assert data.limit == 10
        assert data.top_n == 3
        assert data.k == 30

    def test_missing_query_raises(self):
        with pytest.raises(ValidationError):
            SearchRequest(config_bundle_id=1)

    def test_missing_config_bundle_id_raises(self):
        with pytest.raises(ValidationError):
            SearchRequest(query="q")


class TestSearchResultResponse:

    def test_valid(self):
        data = SearchResultResponse(id="abc", score=0.95, payload={"text": "hello"})
        assert data.id == "abc"
        assert data.score == 0.95
        assert data.payload == {"text": "hello"}

    def test_empty_payload_is_valid(self):
        data = SearchResultResponse(id="x", score=0.0, payload={})
        assert data.payload == {}

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            SearchResultResponse(score=0.5, payload={})


class TestKnowledgePackCreate:

    def test_valid(self):
        data = KnowledgePackCreate(
            name="Backend Pack", domain_id=1,
            description="Reference material", slug="backend-pack",
        )
        assert data.slug == "backend-pack"

    def test_missing_slug_raises(self):
        with pytest.raises(ValidationError):
            KnowledgePackCreate(name="x", domain_id=1, description="d")

    def test_missing_domain_id_raises(self):
        with pytest.raises(ValidationError):
            KnowledgePackCreate(name="x", description="d", slug="s")


class TestKnowledgePackRead:

    def test_from_orm(self):
        obj = orm_mock(id=1, name="Pack", slug="pack-slug", domain_id=2, description="d", version=3)
        data = KnowledgePackRead.model_validate(obj)
        assert data.version == 3
        assert data.slug == "pack-slug"

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            KnowledgePackRead(name="x", slug="s", domain_id=1, description="d", version=1)


class TestSkillCreate:

    def test_valid_with_domain_ids(self):
        data = SkillCreate(skill_name="summarization", description="Summarize", domain_ids=[1, 2])
        assert data.domain_ids == [1, 2]

    def test_domain_ids_defaults_to_empty_list(self):
        data = SkillCreate(skill_name="s", description="d")
        assert data.domain_ids == []

    def test_missing_skill_name_raises(self):
        with pytest.raises(ValidationError):
            SkillCreate(description="d")

    def test_missing_description_raises(self):
        with pytest.raises(ValidationError):
            SkillCreate(skill_name="s")


class TestSkillRead:

    def test_from_orm(self):
        obj = orm_mock(id=1, skill_name="summarization", description="Summarize text", skill_selected_freq=42)
        data = SkillRead.model_validate(obj)
        assert data.skill_selected_freq == 42

    def test_missing_skill_selected_freq_raises(self):
        with pytest.raises(ValidationError):
            SkillRead(id=1, skill_name="x", description="y")


class TestToolCreate:

    def test_valid_with_domain_ids(self):
        data = ToolCreate(tool_name="web_search", description="Search", domain_ids=[3])
        assert data.domain_ids == [3]

    def test_domain_ids_defaults_to_empty_list(self):
        data = ToolCreate(tool_name="t", description="d")
        assert data.domain_ids == []

    def test_missing_tool_name_raises(self):
        with pytest.raises(ValidationError):
            ToolCreate(description="d")

    def test_missing_description_raises(self):
        with pytest.raises(ValidationError):
            ToolCreate(tool_name="t")


class TestToolRead:

    def test_from_orm(self):
        obj = orm_mock(id=1, tool_name="web_search", description="Search", tool_selected_freq=10)
        data = ToolRead.model_validate(obj)
        assert data.tool_selected_freq == 10

    def test_missing_tool_selected_freq_raises(self):
        with pytest.raises(ValidationError):
            ToolRead(id=1, tool_name="x", description="y")


class TestUserCreate:

    def test_valid(self):
        data = UserCreate(username="alice", email="alice@example.com", password="secret")
        assert data.username == "alice"

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(username="alice", email="not-an-email", password="secret")

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(username="alice", email="alice@example.com")

    def test_missing_username_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(email="alice@example.com", password="secret")


class TestUserUpdate:

    def test_all_fields_none_by_default(self):
        data = UserUpdate()
        assert data.username is None
        assert data.email is None

    def test_partial_update_username_only(self):
        data = UserUpdate(username="bob")
        assert data.username == "bob"
        assert data.email is None

    def test_partial_update_email_only(self):
        data = UserUpdate(email="bob@example.com")
        assert data.email == "bob@example.com"
        assert data.username is None

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            UserUpdate(email="bad-email")


class TestChangePassword:

    def test_valid(self):
        data = ChangePassword(old_password="old", new_password="new")
        assert data.old_password == "old"
        assert data.new_password == "new"

    def test_missing_old_password_raises(self):
        with pytest.raises(ValidationError):
            ChangePassword(new_password="new")

    def test_missing_new_password_raises(self):
        with pytest.raises(ValidationError):
            ChangePassword(old_password="old")


class TestUserRead:

    def test_from_orm(self):
        obj = orm_mock(
            id=1, username="alice", email="alice@example.com",
            tokens_used=500, token_limit=10_000,
        )
        data = UserRead.model_validate(obj)
        assert data.tokens_used == 500
        assert data.token_limit == 10_000

    def test_missing_tokens_used_raises(self):
        with pytest.raises(ValidationError):
            UserRead(id=1, username="x", email="x@x.com", token_limit=100)

    def test_missing_token_limit_raises(self):
        with pytest.raises(ValidationError):
            UserRead(id=1, username="x", email="x@x.com", tokens_used=0)