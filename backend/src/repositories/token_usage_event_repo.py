from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func

from src.db.models.token_usage_events import TokenUsageEvent
from src.db.models.users import User
from src.repositories.base_repo import BaseRepository

class TokenUsageEventRepository(BaseRepository[TokenUsageEvent]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, TokenUsageEvent)

    async def report_usage(
        self,
        user: User,
        tokens_used: int,
        agent_id: Optional[int] = None,
    ) -> TokenUsageEvent:

        await self.session.refresh(user, attribute_names=["tokens_used"])

        event = await self.create(
            user_id = user.id,
            tokens_used = tokens_used,
            agent_id = agent_id,
        )

        user.tokens_used += tokens_used
        await self.session.flush()
        return event

    async def get_usage_for_user(self, user_id: int) -> list[TokenUsageEvent]:

        result = await self.session.execute(
            select(TokenUsageEvent)
            .where(TokenUsageEvent.user_id == user_id)
            .order_by(TokenUsageEvent.reported_at.desc())
        )

        return list(result.scalars().all())

    async def get_total_used(self, user_id: int) -> int:
        result = await self.session.execute(
            select(func.sum(TokenUsageEvent.tokens_used))
            .where(TokenUsageEvent.user_id == user_id)
        )
        return result.scalar_one() or 0

    async def is_limit_exceeded(self, user: User) -> bool:
        await self.session.refresh(user, attribute_names=["tokens_used", "token_limit"])
        return user.tokens_used >= user.token_limit