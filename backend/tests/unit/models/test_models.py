import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError, StatementError

from src.db.models.users import User
from src.db.models.agent_profiles import AgentProfile
from src.db.models.skills import Skill
from src.db.models.tools_definition import ToolDefinition
from src.db.models.config_bundles import ConfigBundle
from src.db.models.token_usage_events import TokenUsageEvent
from src.db.models.device_code import DeviceCode
from src.db.models.agent_profile_skills import AgentProfileSkill
from src.db.models.agent_profile_tools import AgentProfileTool
from src.db.models.config_bundle_skills import ConfigBundleSkill
from src.db.models.config_bunlde_tools import ConfigBundleTool
from src.db.models.config_bundle_knowledge_packs import ConfigBundleKnowledgePack
from src.db.enums.device_code_status import DeviceStatus
from src.db.models.knowledge_domains import KnowledgeDomain
from src.db.models.knowledge_packs import KnowledgePack
from src.db.models.skills_domain import SkillDomain
from src.db.models.tool_domain import ToolDomain
from src.db.models.tags import Tag
from src.db.models.document import Document
from src.db.models.document_chunks import DocumentChunk
from src.db.models.document_tags import DocumentTag
from src.db.models.skill_usage_events import SkillUsageEvent
from src.db.models.tool_usage_events import ToolUsageEvent
from src.db.models.discovered_document import DiscoveredDocument
from src.db.enums.document_status import DocumentStatus
from src.db.enums.document_type import DocumentType
from src.db.enums.discovery_type import DiscoveredDocumentDecision
from src.schemas.discovered_document import DiscoveredDocumentCreate

pytestmark = pytest.mark.unit


async def test_user_creation(db_session):
    user = User(username="john", email="john@example.com", password_hash="hashed")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.username == "john"
    assert user.email == "john@example.com"
    assert user.password_hash == "hashed"
    assert user.created_at is not None
    assert user.token_limit == 100_000
    assert user.tokens_used == 0


async def test_user_username_must_be_unique(db_session, sample_user):
    duplicate = User(username=sample_user.username, email="different@example.com", password_hash="hashed")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_user_email_must_be_unique(db_session, sample_user):
    duplicate = User(username="different_username", email=sample_user.email, password_hash="hashed")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_user_repr(sample_user):
    assert repr(sample_user) == f"<User id={sample_user.id} username={sample_user.username}>"


async def test_skill_creation(db_session):
    skill = Skill(
        skill_name="summarization",
        description="Summarizes text",
    )
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)

    assert skill.id is not None
    assert skill.skill_name == "summarization"
    assert skill.skill_selected_freq == 0
    assert skill.domains == []


async def test_skill_can_be_created_without_domain(db_session, sample_skill):
    assert sample_skill.domains == []


async def test_skill_name_must_be_unique_globally(db_session, sample_skill):
    duplicate = Skill(
        skill_name=sample_skill.skill_name,
        description="Another description",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_skill_repr(sample_skill):
    assert repr(sample_skill) == f"<Skill id={sample_skill.id} name={sample_skill.skill_name}>"


async def test_skill_domains_relationship(db_session, sample_skill, sample_knowledge_domain):
    sample_skill.domains.append(sample_knowledge_domain)
    db_session.add(sample_skill)
    await db_session.commit()
    await db_session.refresh(sample_skill)

    assert sample_knowledge_domain in sample_skill.domains
    assert sample_skill in sample_knowledge_domain.skills


async def test_skill_can_belong_to_multiple_domains(
    db_session, sample_skill, sample_knowledge_domain, another_knowledge_domain
):
    sample_skill.domains.extend([sample_knowledge_domain, another_knowledge_domain])
    db_session.add(sample_skill)
    await db_session.commit()
    await db_session.refresh(sample_skill)

    assert {d.id for d in sample_skill.domains} == {
        sample_knowledge_domain.id,
        another_knowledge_domain.id,
    }


async def test_skill_domain_link_row_exists(db_session, skill_with_domain, sample_knowledge_domain):
    link = await db_session.get(SkillDomain, (skill_with_domain.id, sample_knowledge_domain.id))
    assert link is not None


async def test_deleting_domain_removes_skill_domain_link_but_not_skill(
    db_session, skill_with_domain, sample_knowledge_domain
):
    skill_id, domain_id = skill_with_domain.id, sample_knowledge_domain.id

    await db_session.delete(sample_knowledge_domain)
    await db_session.commit()

    link = await db_session.get(SkillDomain, (skill_id, domain_id))
    assert link is None

    remaining_skill = await db_session.get(Skill, skill_id)
    assert remaining_skill is not None


async def test_deleting_skill_removes_skill_domain_link_but_not_domain(
    db_session, skill_with_domain, sample_knowledge_domain
):
    skill_id, domain_id = skill_with_domain.id, sample_knowledge_domain.id

    await db_session.delete(skill_with_domain)
    await db_session.commit()

    link = await db_session.get(SkillDomain, (skill_id, domain_id))
    assert link is None

    remaining_domain = await db_session.get(KnowledgeDomain, domain_id)
    assert remaining_domain is not None


async def test_tool_creation(db_session):
    tool = ToolDefinition(tool_name="web_search", description="Searches the web")
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)

    assert tool.id is not None
    assert tool.tool_name == "web_search"
    assert tool.tool_selected_freq == 0


async def test_tool_name_must_be_unique(db_session, sample_tool):
    duplicate = ToolDefinition(tool_name=sample_tool.tool_name, description="Another description")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_tool_repr(sample_tool):
    assert repr(sample_tool) == f"<ToolDefinition id={sample_tool.id} name={sample_tool.tool_name}>"


async def test_tool_can_be_created_without_domain(db_session, sample_tool):
    assert sample_tool.domains == []


async def test_tool_can_be_scoped_to_domain(db_session, domain_scoped_tool, another_knowledge_domain):
    assert another_knowledge_domain in domain_scoped_tool.domains
    assert domain_scoped_tool in another_knowledge_domain.tools


async def test_tool_domain_link_row_exists(db_session, domain_scoped_tool, another_knowledge_domain):
    link = await db_session.get(ToolDomain, (domain_scoped_tool.id, another_knowledge_domain.id))
    assert link is not None


async def test_deleting_domain_removes_tool_domain_link_but_not_tool(
    db_session, domain_scoped_tool, another_knowledge_domain
):
    tool_id, domain_id = domain_scoped_tool.id, another_knowledge_domain.id

    await db_session.delete(another_knowledge_domain)
    await db_session.commit()

    link = await db_session.get(ToolDomain, (tool_id, domain_id))
    assert link is None

    remaining_tool = await db_session.get(ToolDefinition, tool_id)
    assert remaining_tool is not None


async def test_agent_profile_creation(db_session):
    agent = AgentProfile(agent_name="assistant", description="A helpful assistant")
    db_session.add(agent)
    await db_session.commit()
    await db_session.refresh(agent)

    assert agent.id is not None
    assert agent.agent_name == "assistant"


async def test_agent_profile_name_must_be_unique(db_session, sample_agent_profile):
    duplicate = AgentProfile(agent_name=sample_agent_profile.agent_name, description="Another description")
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_agent_profile_repr(sample_agent_profile):
    assert repr(sample_agent_profile) == f"<AgentProfile id={sample_agent_profile.id} name={sample_agent_profile.agent_name}>"


async def test_agent_profile_skills_relationship(db_session, sample_agent_profile, sample_skill):
    sample_agent_profile.skills.append(sample_skill)
    db_session.add(sample_agent_profile)
    await db_session.commit()
    await db_session.refresh(sample_agent_profile)

    assert sample_skill in sample_agent_profile.skills
    assert sample_agent_profile in sample_skill.agent_profiles


async def test_agent_profile_tools_relationship(db_session, sample_agent_profile, sample_tool):
    sample_agent_profile.tools.append(sample_tool)
    db_session.add(sample_agent_profile)
    await db_session.commit()
    await db_session.refresh(sample_agent_profile)

    assert sample_tool in sample_agent_profile.tools
    assert sample_agent_profile in sample_tool.agent_profiles


async def test_config_bundle_creation(db_session, sample_user, sample_agent_profile):
    bundle = ConfigBundle(
        user_id=sample_user.id,
        agent_id=sample_agent_profile.id,
        name="default-bundle",
        description="Default configuration",
    )
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)

    assert bundle.id is not None
    assert bundle.created_at is not None
    assert bundle.user_id == sample_user.id
    assert bundle.agent_id == sample_agent_profile.id


async def test_config_bundle_name_unique_per_user(db_session, sample_config_bundle):
    duplicate = ConfigBundle(
        user_id=sample_config_bundle.user_id,
        agent_id=sample_config_bundle.agent_id,
        name=sample_config_bundle.name,
        description="Another description",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_config_bundle_same_name_allowed_for_different_users(
    db_session, sample_config_bundle, another_user, sample_agent_profile
):
    bundle = ConfigBundle(
        user_id=another_user.id,
        agent_id=sample_agent_profile.id,
        name=sample_config_bundle.name,
        description="Same name, different user",
    )
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)

    assert bundle.id is not None


async def test_config_bundle_user_relationship(db_session, sample_config_bundle, sample_user):
    await db_session.refresh(sample_user, attribute_names=["configs"])
    assert sample_config_bundle in sample_user.configs
    assert sample_config_bundle.user.id == sample_user.id


async def test_config_bundle_skills_relationship(db_session, sample_config_bundle, sample_skill):
    sample_config_bundle.skills.append(sample_skill)
    db_session.add(sample_config_bundle)
    await db_session.commit()
    await db_session.refresh(sample_config_bundle)

    assert sample_skill in sample_config_bundle.skills
    assert sample_config_bundle in sample_skill.config_bundles


async def test_config_bundle_tools_relationship(db_session, sample_config_bundle, sample_tool):
    sample_config_bundle.tools.append(sample_tool)
    db_session.add(sample_config_bundle)
    await db_session.commit()
    await db_session.refresh(sample_config_bundle)

    assert sample_tool in sample_config_bundle.tools
    assert sample_config_bundle in sample_tool.config_bundles


async def test_config_bundle_knowledge_packs_relationship(
    db_session, sample_config_bundle, sample_knowledge_pack
):
    sample_config_bundle.knowledge_packs.append(sample_knowledge_pack)
    db_session.add(sample_config_bundle)
    await db_session.commit()
    await db_session.refresh(sample_config_bundle)

    assert sample_knowledge_pack in sample_config_bundle.knowledge_packs
    assert sample_config_bundle in sample_knowledge_pack.config_bundles


async def test_config_bundle_knowledge_pack_link_row_exists(
    db_session, config_bundle_with_knowledge_pack, sample_knowledge_pack
):
    link = await db_session.get(
        ConfigBundleKnowledgePack,
        (config_bundle_with_knowledge_pack.id, sample_knowledge_pack.id),
    )
    assert link is not None


async def test_deleting_config_bundle_removes_knowledge_pack_link_but_not_pack(
    db_session, config_bundle_with_knowledge_pack, sample_knowledge_pack
):
    bundle_id, pack_id = config_bundle_with_knowledge_pack.id, sample_knowledge_pack.id

    await db_session.delete(config_bundle_with_knowledge_pack)
    await db_session.commit()

    link = await db_session.get(ConfigBundleKnowledgePack, (bundle_id, pack_id))
    assert link is None

    remaining_pack = await db_session.get(KnowledgePack, pack_id)
    assert remaining_pack is not None


async def test_config_bundle_repr(sample_config_bundle):
    assert repr(sample_config_bundle) == f"<ConfigBundle id={sample_config_bundle.id} name={sample_config_bundle.name}>"


async def test_deleting_user_cascades_config_bundles(db_session, sample_user, sample_config_bundle):
    await db_session.delete(sample_user)
    await db_session.commit()

    result = await db_session.get(ConfigBundle, sample_config_bundle.id, populate_existing=True)
    assert result is None


async def test_deleting_agent_profile_cascades_config_bundles(db_session, sample_agent_profile, sample_config_bundle):
    await db_session.delete(sample_agent_profile)
    await db_session.commit()

    result = await db_session.get(ConfigBundle, sample_config_bundle.id, populate_existing=True)
    assert result is None


async def test_token_usage_event_creation(db_session, sample_user, sample_agent_profile):
    event = TokenUsageEvent(
        user_id=sample_user.id,
        agent_id=sample_agent_profile.id,
        tokens_used=250,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    assert event.id is not None
    assert event.tokens_used == 250
    assert event.reported_at is not None


async def test_token_usage_event_agent_id_is_nullable(db_session, sample_user):
    event = TokenUsageEvent(user_id=sample_user.id, agent_id=None, tokens_used=100)
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    assert event.agent_id is None


async def test_token_usage_event_user_relationship(db_session, sample_token_usage_event, sample_user):
    await db_session.refresh(sample_user, attribute_names=["token_usage_events"])
    assert sample_token_usage_event in sample_user.token_usage_events
    assert sample_token_usage_event.user.id == sample_user.id


async def test_deleting_user_cascades_token_usage_events(db_session, sample_user, sample_token_usage_event):
    await db_session.delete(sample_user)
    await db_session.commit()

    result = await db_session.get(TokenUsageEvent, sample_token_usage_event.id, populate_existing=True)
    assert result is None


async def test_device_code_creation(db_session, sample_user):
    from datetime import timedelta

    device_code = DeviceCode(
        device_code="XYZ1-2345",
        user_id=sample_user.id,
        scope="read write",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        interval=5,
    )
    db_session.add(device_code)
    await db_session.commit()
    await db_session.refresh(device_code)

    assert device_code.id is not None
    assert device_code.status == DeviceStatus.PENDING


async def test_device_code_value_must_be_unique(db_session, sample_device_code):
    from datetime import timedelta

    duplicate = DeviceCode(
        device_code=sample_device_code.device_code,
        user_id=sample_device_code.user_id,
        scope="read",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        interval=5,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_device_code_status_transition(db_session, sample_device_code):
    sample_device_code.status = DeviceStatus.APPROVED
    db_session.add(sample_device_code)
    await db_session.commit()
    await db_session.refresh(sample_device_code)

    assert sample_device_code.status == DeviceStatus.APPROVED


async def test_device_code_repr(sample_device_code):
    text = repr(sample_device_code)
    assert "DeviceCode" in text
    assert sample_device_code.device_code in text


async def test_agent_profile_skill_link_row_exists(db_session, sample_agent_profile, sample_skill):
    sample_agent_profile.skills.append(sample_skill)
    db_session.add(sample_agent_profile)
    await db_session.commit()

    link = await db_session.get(AgentProfileSkill, (sample_agent_profile.id, sample_skill.id))
    assert link is not None


async def test_agent_profile_tool_link_row_exists(db_session, sample_agent_profile, sample_tool):
    sample_agent_profile.tools.append(sample_tool)
    db_session.add(sample_agent_profile)
    await db_session.commit()

    link = await db_session.get(AgentProfileTool, (sample_agent_profile.id, sample_tool.id))
    assert link is not None


async def test_config_bundle_skill_link_row_exists(db_session, sample_config_bundle, sample_skill):
    sample_config_bundle.skills.append(sample_skill)
    db_session.add(sample_config_bundle)
    await db_session.commit()

    link = await db_session.get(ConfigBundleSkill, (sample_config_bundle.id, sample_skill.id))
    assert link is not None


async def test_config_bundle_tool_link_row_exists(db_session, sample_config_bundle, sample_tool):
    sample_config_bundle.tools.append(sample_tool)
    db_session.add(sample_config_bundle)
    await db_session.commit()

    link = await db_session.get(ConfigBundleTool, (sample_config_bundle.id, sample_tool.id))
    assert link is not None


async def test_deleting_agent_profile_cascades_skill_links(db_session, sample_agent_profile, sample_skill):
    sample_agent_profile.skills.append(sample_skill)
    db_session.add(sample_agent_profile)
    await db_session.commit()

    agent_id, skill_id = sample_agent_profile.id, sample_skill.id
    await db_session.delete(sample_agent_profile)
    await db_session.commit()

    link = await db_session.get(AgentProfileSkill, (agent_id, skill_id))
    assert link is None

    remaining_skill = await db_session.get(Skill, skill_id)
    assert remaining_skill is not None


async def test_knowledge_domain_creation(db_session):
    domain = KnowledgeDomain(
        slug="testing-strategy",
        name="Testing Strategy",
        description="Test design across languages",
    )
    db_session.add(domain)
    await db_session.commit()
    await db_session.refresh(domain)

    assert domain.id is not None
    assert domain.slug == "testing-strategy"
    assert repr(domain) == f"<KnowledgeDomain id={domain.id} slug={domain.slug}>"


async def test_knowledge_domain_slug_must_be_unique(db_session, sample_knowledge_domain):
    duplicate = KnowledgeDomain(
        slug=sample_knowledge_domain.slug,
        name="Duplicate",
        description="Should fail",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_knowledge_domain_parent_child_relationship(
    db_session, sample_knowledge_domain, child_knowledge_domain
):
    await db_session.refresh(sample_knowledge_domain, attribute_names=["children"])

    assert child_knowledge_domain in sample_knowledge_domain.children
    assert child_knowledge_domain.parent_domain_id == sample_knowledge_domain.id


async def test_deleting_parent_domain_cascades_child_domain(
    db_session, sample_knowledge_domain, child_knowledge_domain
):
    child_id = child_knowledge_domain.id

    await db_session.delete(sample_knowledge_domain)
    await db_session.commit()

    result = await db_session.get(KnowledgeDomain, child_id, populate_existing=True)
    assert result is None


async def test_knowledge_domain_skills_relationship(db_session, skill_with_domain, sample_knowledge_domain):
    await db_session.refresh(sample_knowledge_domain, attribute_names=["skills"])
    assert skill_with_domain in sample_knowledge_domain.skills


async def test_knowledge_domain_tools_relationship(db_session, domain_scoped_tool, another_knowledge_domain):
    await db_session.refresh(another_knowledge_domain, attribute_names=["tools"])
    assert domain_scoped_tool in another_knowledge_domain.tools


async def test_knowledge_domain_knowledge_packs_relationship(
    db_session, sample_knowledge_domain, sample_knowledge_pack
):
    await db_session.refresh(sample_knowledge_domain, attribute_names=["knowledge_packs"])
    assert sample_knowledge_pack in sample_knowledge_domain.knowledge_packs
    assert sample_knowledge_pack.domain.id == sample_knowledge_domain.id


async def test_knowledge_pack_creation(db_session, sample_knowledge_pack, sample_knowledge_domain):
    assert sample_knowledge_pack.id is not None
    assert sample_knowledge_pack.slug == "backend-api-design-pack"
    assert sample_knowledge_pack.version == 1
    assert sample_knowledge_pack.domain_id == sample_knowledge_domain.id
    assert sample_knowledge_pack.created_at is not None


async def test_knowledge_pack_slug_must_be_unique(db_session, sample_knowledge_pack):
    duplicate = KnowledgePack(
        slug=sample_knowledge_pack.slug,
        name="Different name",
        domain_id=sample_knowledge_pack.domain_id,
        description="Should fail on slug",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_knowledge_pack_name_unique_per_domain(db_session, sample_knowledge_pack):
    duplicate = KnowledgePack(
        slug="different-slug",
        name=sample_knowledge_pack.name,
        domain_id=sample_knowledge_pack.domain_id,
        description="Should fail on domain+name",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_knowledge_pack_same_name_allowed_in_different_domain(
    db_session, sample_knowledge_pack, another_knowledge_domain
):
    pack = KnowledgePack(
        slug="different-slug-again",
        name=sample_knowledge_pack.name,
        domain_id=another_knowledge_domain.id,
        description="Same name, different domain",
    )
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)

    assert pack.id is not None
    assert pack.id != sample_knowledge_pack.id


async def test_knowledge_pack_repr(sample_knowledge_pack):
    assert repr(sample_knowledge_pack) == f"<KnowledgePack id={sample_knowledge_pack.id} slug={sample_knowledge_pack.slug}>"


async def test_knowledge_pack_requires_domain(db_session):
    pack = KnowledgePack(
        slug="orphan-pack",
        name="Orphan Pack",
        description="Missing domain_id",
    )
    db_session.add(pack)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_domain_cascades_knowledge_packs(
    db_session, sample_knowledge_domain, sample_knowledge_pack
):
    pack_id = sample_knowledge_pack.id

    await db_session.delete(sample_knowledge_domain)
    await db_session.commit()

    result = await db_session.get(KnowledgePack, pack_id, populate_existing=True)
    assert result is None


async def test_tag_creation(db_session):
    tag = Tag(tag_name="system-design")
    db_session.add(tag)
    await db_session.commit()
    await db_session.refresh(tag)

    assert tag.id is not None
    assert tag.tag_name == "system-design"


async def test_tag_name_must_be_unique(db_session, sample_tag):
    duplicate = Tag(tag_name=sample_tag.tag_name)
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_document_tags_relationship(db_session, sample_document, sample_tag, another_tag):
    sample_document.tags.append(sample_tag)
    sample_document.tags.append(another_tag)
    db_session.add(sample_document)
    await db_session.commit()
    await db_session.refresh(sample_document)

    assert sample_tag in sample_document.tags
    assert another_tag in sample_document.tags
    assert sample_document in sample_tag.documents


async def test_deleting_document_cascades_document_tag_link(
    db_session, sample_document, sample_tag
):
    sample_document.tags.append(sample_tag)
    db_session.add(sample_document)
    await db_session.commit()

    document_id, tag_id = sample_document.id, sample_tag.id
    await db_session.delete(sample_document)
    await db_session.commit()

    link = await db_session.get(DocumentTag, (document_id, tag_id))
    assert link is None

    remaining_tag = await db_session.get(Tag, tag_id)
    assert remaining_tag is not None


async def test_document_creation_unclassified(db_session, sample_document):
    assert sample_document.id is not None
    assert sample_document.knowledge_pack_id is None
    assert sample_document.status == DocumentStatus.PENDING
    assert sample_document.version == 1


async def test_document_creation_classified(db_session, classified_document, sample_knowledge_pack):
    assert classified_document.knowledge_pack_id == sample_knowledge_pack.id
    assert classified_document.knowledge_pack.id == sample_knowledge_pack.id
    assert classified_document.status == DocumentStatus.INDEXED


async def test_document_unique_source_hash_version(db_session, sample_document):
    duplicate = Document(
        source=sample_document.source,
        document_type=DocumentType.BOOK,
        size=1,
        content_hash=sample_document.content_hash,
        version=sample_document.version,
        scraped_at=sample_document.scraped_at,
        embedding_model="text-embedding-3-large",
        knowledge_type=sample_document.knowledge_type,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_document_reindex_new_version_allowed(db_session, sample_document):
    new_version = Document(
        source=sample_document.source,
        document_type=sample_document.document_type,
        size=sample_document.size,
        content_hash=sample_document.content_hash,
        version=sample_document.version + 1,
        scraped_at=sample_document.scraped_at,
        embedding_model=sample_document.embedding_model,
        knowledge_type=sample_document.knowledge_type,
    )
    db_session.add(new_version)
    await db_session.commit()
    await db_session.refresh(new_version)

    assert new_version.id is not None
    assert new_version.id != sample_document.id


async def test_deleting_knowledge_pack_sets_document_knowledge_pack_id_null(
    db_session, classified_document, sample_knowledge_pack
):
    await db_session.delete(sample_knowledge_pack)
    await db_session.commit()

    result = await db_session.get(Document, classified_document.id, populate_existing=True)
    assert result is not None
    assert result.knowledge_pack_id is None


async def test_deleting_domain_cascades_to_documents_via_knowledge_pack(
    db_session, sample_knowledge_domain, classified_document
):
    document_id = classified_document.id

    await db_session.delete(sample_knowledge_domain)
    await db_session.commit()

    result = await db_session.get(Document, document_id, populate_existing=True)
    assert result is not None
    assert result.knowledge_pack_id is None


async def test_document_chunk_creation(db_session, sample_document_chunk, classified_document):
    assert sample_document_chunk.id is not None
    assert sample_document_chunk.document_id == classified_document.id
    assert repr(sample_document_chunk) == (
        f"<DocumentChunk id={sample_document_chunk.id} "
        f"document_id={sample_document_chunk.document_id} "
        f"chunk_index={sample_document_chunk.chunk_index}>"
    )


async def test_document_chunk_unique_index_per_document(db_session, sample_document_chunk, classified_document):
    duplicate = DocumentChunk(
        document_id=classified_document.id,
        chunk_index=sample_document_chunk.chunk_index,
        qdrant_point_id="point-0002",
        token_count=256,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_document_chunk_qdrant_point_id_must_be_unique(db_session, sample_document_chunk, classified_document):
    duplicate = DocumentChunk(
        document_id=classified_document.id,
        chunk_index=sample_document_chunk.chunk_index + 1,
        qdrant_point_id=sample_document_chunk.qdrant_point_id,
        token_count=256,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_document_cascades_chunks(db_session, sample_document_chunk, classified_document):
    chunk_id = sample_document_chunk.id
    await db_session.delete(classified_document)
    await db_session.commit()

    result = await db_session.get(DocumentChunk, chunk_id, populate_existing=True)
    assert result is None


async def test_skill_usage_event_creation(db_session, sample_skill_usage_event, sample_skill, sample_user):
    assert sample_skill_usage_event.id is not None
    assert sample_skill_usage_event.skill_id == sample_skill.id
    assert sample_skill_usage_event.user_id == sample_user.id
    assert sample_skill_usage_event.selected_at is not None


async def test_skill_usage_event_config_bundle_is_nullable(db_session, sample_skill, sample_user):
    event = SkillUsageEvent(skill_id=sample_skill.id, user_id=sample_user.id, config_bundle_id=None)
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    assert event.config_bundle_id is None


async def test_deleting_skill_cascades_usage_events(db_session, sample_skill_usage_event, sample_skill):
    event_id = sample_skill_usage_event.id
    await db_session.delete(sample_skill)
    await db_session.commit()

    result = await db_session.get(SkillUsageEvent, event_id, populate_existing=True)
    assert result is None


async def test_deleting_config_bundle_sets_skill_usage_event_config_bundle_id_null(
    db_session, sample_skill_usage_event, sample_config_bundle
):
    await db_session.delete(sample_config_bundle)
    await db_session.commit()

    result = await db_session.get(SkillUsageEvent, sample_skill_usage_event.id, populate_existing=True)
    assert result is not None
    assert result.config_bundle_id is None


async def test_tool_usage_event_creation(db_session, sample_tool_usage_event, sample_tool, sample_user):
    assert sample_tool_usage_event.id is not None
    assert sample_tool_usage_event.tool_id == sample_tool.id
    assert sample_tool_usage_event.user_id == sample_user.id


async def test_deleting_tool_cascades_usage_events(db_session, sample_tool_usage_event, sample_tool):
    event_id = sample_tool_usage_event.id
    await db_session.delete(sample_tool)
    await db_session.commit()

    result = await db_session.get(ToolUsageEvent, event_id, populate_existing=True)
    assert result is None


def unique_hash() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def make_discovered(**overrides) -> DiscoveredDocument:
    values = dict(
        url="https://example.com/guide",
        url_hash=unique_hash(),
        decision=DiscoveredDocumentDecision.ACCEPT,
    )
    values.update(overrides)
    return DiscoveredDocument(**values)


@pytest_asyncio.fixture
async def sample_discovered_document(db_session):
    document = make_discovered(
        url="https://example.com/event-sourcing",
        trust_score=0.825,
        educational_score=0.9,
        implementation_score=0.8,
        authority_score=0.7,
        document_category="tutorial",
        reason="Covers snapshots and upcasting with a worked example.",
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return document


async def test_discovered_document_creation(db_session, sample_discovered_document):
    document = sample_discovered_document

    assert document.id is not None
    assert document.url == "https://example.com/event-sourcing"
    assert len(document.url_hash) == 64
    assert document.decision == DiscoveredDocumentDecision.ACCEPT
    assert document.trust_score == pytest.approx(0.825)
    assert document.educational_score == pytest.approx(0.9)
    assert document.implementation_score == pytest.approx(0.8)
    assert document.authority_score == pytest.approx(0.7)
    assert document.document_category == "tutorial"
    assert document.reason == "Covers snapshots and upcasting with a worked example."


async def test_discovered_document_optional_fields_default_to_null(db_session):
    document = make_discovered()
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    assert document.trust_score is None
    assert document.educational_score is None
    assert document.implementation_score is None
    assert document.authority_score is None
    assert document.document_category is None
    assert document.reason is None


async def test_discovered_document_created_at_is_set_by_database(db_session, sample_discovered_document):
    created_at = sample_discovered_document.created_at

    assert created_at is not None
    assert created_at.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - created_at).total_seconds()) < 300


@pytest.mark.parametrize("decision", list(DiscoveredDocumentDecision))
async def test_discovered_document_decision_round_trip(db_session, decision):
    document = make_discovered(decision=decision)
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    assert document.decision is decision


async def test_discovered_document_can_be_filtered_by_decision(db_session):
    accepted = make_discovered(decision=DiscoveredDocumentDecision.ACCEPT)
    rejected = make_discovered(decision=DiscoveredDocumentDecision.REJECT)
    db_session.add_all([accepted, rejected])
    await db_session.commit()

    result = await db_session.execute(
        select(DiscoveredDocument.id).where(
            DiscoveredDocument.decision == DiscoveredDocumentDecision.REJECT
        )
    )

    assert result.scalars().all() == [rejected.id]


async def test_discovered_document_invalid_decision_is_rejected(db_session):
    document = make_discovered(decision="maybe")
    db_session.add(document)

    with pytest.raises(StatementError):
        await db_session.commit()
    await db_session.rollback()


async def test_discovered_document_url_hash_must_be_unique(db_session, sample_discovered_document):
    duplicate = make_discovered(
        url="https://different.example.com/page",
        url_hash=sample_discovered_document.url_hash,
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_discovered_document_same_url_with_different_hash_is_allowed(
    db_session, sample_discovered_document
):
    second = make_discovered(url=sample_discovered_document.url, url_hash=unique_hash())
    db_session.add(second)
    await db_session.commit()
    await db_session.refresh(second)

    assert second.id != sample_discovered_document.id


@pytest.mark.parametrize("field", ["url", "url_hash", "decision"])
async def test_discovered_document_required_fields_cannot_be_null(db_session, field):
    document = make_discovered(**{field: None})
    db_session.add(document)

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_discovered_document_url_hash_accepts_exactly_64_chars(db_session):
    document = make_discovered(url_hash="f" * 64)
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    assert document.url_hash == "f" * 64


async def test_discovered_document_url_hash_longer_than_64_chars_is_rejected(db_session):
    document = make_discovered(url_hash="f" * 65)
    db_session.add(document)

    with pytest.raises(DataError):
        await db_session.commit()
    await db_session.rollback()


async def test_discovered_document_category_accepts_exactly_100_chars(db_session):
    document = make_discovered(document_category="c" * 100)
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    assert len(document.document_category) == 100


async def test_discovered_document_category_longer_than_100_chars_is_rejected(db_session):
    document = make_discovered(document_category="c" * 101)
    db_session.add(document)

    with pytest.raises(DataError):
        await db_session.commit()
    await db_session.rollback()


async def test_discovered_document_url_and_reason_are_unbounded_text(db_session):
    long_url = "https://example.com/" + "a" * 5000
    long_reason = "reason " * 5000
    document = make_discovered(url=long_url, reason=long_reason)
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    assert document.url == long_url
    assert document.reason == long_reason


@pytest.mark.parametrize("score", [0.0, 0.5, 1.0])
async def test_discovered_document_score_values_round_trip(db_session, score):
    document = make_discovered(
        trust_score=score,
        educational_score=score,
        implementation_score=score,
        authority_score=score,
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    assert document.trust_score == pytest.approx(score)
    assert document.educational_score == pytest.approx(score)
    assert document.implementation_score == pytest.approx(score)
    assert document.authority_score == pytest.approx(score)


async def test_discovered_document_can_be_built_from_create_schema(db_session):
    schema = DiscoveredDocumentCreate(
        url="https://example.com/from-schema",
        url_hash=unique_hash(),
        decision=DiscoveredDocumentDecision.REJECT,
        trust_score=0.2,
        educational_score=0.1,
        implementation_score=0.3,
        authority_score=0.4,
        document_category="marketing",
        reason="Landing page without technical content.",
    )

    document = DiscoveredDocument(**schema.model_dump())
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    assert document.id is not None
    assert document.url == schema.url
    assert document.url_hash == schema.url_hash
    assert document.decision == DiscoveredDocumentDecision.REJECT
    assert document.trust_score == pytest.approx(0.2)
    assert document.document_category == "marketing"
    assert document.reason == "Landing page without technical content."


async def test_discovered_document_minimal_create_schema_is_persistable(db_session):
    schema = DiscoveredDocumentCreate(
        url="https://example.com/minimal",
        url_hash=unique_hash(),
        decision=DiscoveredDocumentDecision.ACCEPT,
    )

    document = DiscoveredDocument(**schema.model_dump())
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)

    assert document.trust_score is None
    assert document.reason is None