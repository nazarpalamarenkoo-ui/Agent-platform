from src.repositories.agent_profile_repo import AgentProfileRepository
from src.repositories.skill_repo import SkillRepository
from src.repositories.tool_repo import ToolDefinitionRepository
from src.db.models.agent_profiles import AgentProfile

class AgentProfileService:
    
    def __init__(
        self,
        agent_profile_repo: AgentProfileRepository,
        skill_repo: SkillRepository,
        tool_repo: ToolDefinitionRepository
    ):
        self.agent_repo = agent_profile_repo
        self.skill_repo = skill_repo
        self.tool_repo = tool_repo
        
    async def create_profile(
        self,
        name: str,
        description: str,
        skill_ids: list[int],
        tool_ids: list[int]
    ) -> AgentProfile:
        
        profile = await self.agent_repo.create(
            agent_name=name,
            description=description,
        )

        for skill_id in skill_ids:
            skill = await self.skill_repo.get_by_id(skill_id)
            if not skill:
                raise ValueError(f"Skill {skill_id} not found")
            await self.agent_repo.add_skill(profile, skill)

        for tool_id in tool_ids:
            tool = await self.tool_repo.get_by_id(tool_id)
            if not tool:
                raise ValueError(f"Tool {tool_id} not found")
            await self.agent_repo.add_tool(profile, tool)

        return profile
    
    async def get_profile(self, agent_id: int) -> AgentProfile:
        
        profile = await self.agent_repo.get_by_id(agent_id)
        
        if not profile:
            raise ValueError(f"Agent profile {agent_id} not found")
        return profile
    
    async def get_all_profiles(self, limit: int = 100, offset: int = 0) -> list[AgentProfile]:
        return await self.agent_repo.get_all(limit=limit, offset=offset)