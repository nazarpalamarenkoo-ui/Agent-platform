from typing import Literal

from pydantic import BaseModel, EmailStr

from src.db.enums.user_role import UserRole


class RoleUpdate(BaseModel):
    role: Literal[UserRole.USER, UserRole.ADMIN]


class AdminUserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: UserRole
    model_config = {"from_attributes": True}