from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.base_repo import BaseRepository
from src.db.models.users import User

class UserRepository(BaseRepository[User]):
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, User)
        
    async def get_by_username(self, username: str) -> Optional[User]:
        
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        
        return result.scalar_one_or_none()
    
    async def get_by_email(self, email: str) -> Optional[User]:
        
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        
        return result.scalar_one_or_none()
    
    async def update_password(self, user: User, new_password_hash: str) -> User:
        user.password_hash = new_password_hash
        await self.session.flush()
        return user

    async def reset_usage(self, user: User) -> User:
        
        user.tokens_used = 0
        await self.session.flush()
        return user