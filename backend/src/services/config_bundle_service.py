from typing import Optional

from src.repositories.config_bundle_repo import ConfigBundleRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.repositories.agent_profile_repo import AgentProfileRepository
from src.db.models.config_bundles import ConfigBundle

class ConfigBundleService:
    
    def __init__(
        self,
        config_bundle_repo: ConfigBundleRepository,
        skill_repo: SkillRepository,
        tool_repo: ToolDefinitionRepository,
        knowledge_pack_repo: KnowledgePackRepository,
        agent_profile_repo: AgentProfileRepository
    ):
        self.config_bundle_repo = config_bundle_repo
        self.skill_repo = skill_repo
        self.tool_repo = tool_repo
        self.knowledge_pack_repo = knowledge_pack_repo
        self.agent_profile_repo = agent_profile_repo

    async def create_bundle(
        self,
        user_id: int,
        agent_id: int,
        name: str,
        description: str,
        skill_ids: list[int],
        tool_ids: list[int],
        knowledge_pack_ids: list[int] | None = None,
    ) -> ConfigBundle:
        
        bundle = await self.config_bundle_repo.create(
            user_id=user_id,
            agent_id=agent_id,
            name=name,
            description=description
        )
        
        for skill_id in skill_ids:
            skill = await self.skill_repo.get_by_id(skill_id)
            if not skill:
                raise ValueError(f"Skill with ID {skill_id} does not exist")
            await self.config_bundle_repo.add_skill(bundle, skill)
            
        for tool_id in tool_ids:
            tool = await self.tool_repo.get_by_id(tool_id)
            if not tool:
                raise ValueError(f"Tool with ID {tool_id} does not exist")
            await self.config_bundle_repo.add_tool(bundle, tool)
        
        for pack_id in (knowledge_pack_ids or []):
            pack = await self.knowledge_pack_repo.get_by_id(pack_id)
            if not pack:
                raise ValueError(f"Knowledge pack with ID {pack_id} does not exist")
            await self.config_bundle_repo.add_knowledge_pack(bundle, pack)
            
        return bundle
    
    async def clone_bundle(self, bundle_id: int, user_id: int) -> ConfigBundle:
        
        original = await self.config_bundle_repo.get_by_id_with_relations(bundle_id)
            
        if not original:
            raise ValueError(f"Config bundle with ID {bundle_id} does not exist")
            
        cloned = await self.config_bundle_repo.create(
            user_id=user_id,
            agent_id=original.agent_id,
            name=f"Clone of {original.name}",
            description=original.description
        )
        
        for skill in original.skills:
            await self.config_bundle_repo.add_skill(cloned, skill)
            
        for tool in original.tools:
            await self.config_bundle_repo.add_tool(cloned, tool)
        
        for pack in original.knowledge_packs:
            await self.config_bundle_repo.add_knowledge_pack(cloned, pack)
            
        return cloned
    
    async def create_from_agent(
        self,
        user_id: int,
        agent_id: int,
        name: str,
        description: str
    ) -> ConfigBundle:
        
        agent = await self.agent_profile_repo.get_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent profile with ID {agent_id} does not exist")
        
        bundle = await self.config_bundle_repo.create(
            user_id=user_id,
            agent_id=agent_id,
            name=name,
            description=description
        )
        
        for skill in agent.skills:
            await self.config_bundle_repo.add_skill(bundle, skill)
    
        for tool in agent.tools:
            await self.config_bundle_repo.add_tool(bundle, tool)
        
        return bundle
    
    async def get_user_bundles(
        self,
        user_id: int,
        agent_id: int,
    ) -> list[ConfigBundle]:
        return await self.config_bundle_repo.get_for_user_and_agent(user_id, agent_id)