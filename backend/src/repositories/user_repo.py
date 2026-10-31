from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.base_repo import BaseRepository
from src.db.enums.user_role import UserRole
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

    async def exists_by_email(self, email: str) -> bool:
        result = await self.session.execute(select(User.id).where(User.email == email))
        return result.scalar_one_or_none() is not None

    async def list_page(self, limit: int = 50, offset: int = 0) -> list[User]:
        result = await self.session.execute(
            select(User).order_by(User.id).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def update_password(self, user: User, new_password_hash: str) -> User:
        user.password_hash = new_password_hash
        await self.session.flush()
        return user

    async def reset_usage(self, user: User) -> User:
        user.tokens_used = 0
        await self.session.flush()
        return user

    async def set_token_limit(self, user: User, token_limit: int) -> User:
        user.token_limit = token_limit
        await self.session.flush()
        return user

    async def get_super_admin(self) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.role == UserRole.SUPER_ADMIN)
        )
        return result.scalar_one_or_none()

    async def list_by_roles(self, roles: Sequence[UserRole]) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.role.in_(list(roles))).order_by(User.id)
        )
        return list(result.scalars().all())

    async def set_role(self, user: User, role: UserRole) -> User:
        user.role = role
        await self.session.flush()
        return user