from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from src.db.enums.user_role import UserRole


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None


class ChangePassword(BaseModel):
    old_password: str
    new_password: str


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: UserRole
    tokens_used: int
    token_limit: int
    model_config = {"from_attributes": True}


class AdminUserRead(UserRead):
    created_at: datetime


class RoleUpdate(BaseModel):
    role: Literal[UserRole.USER, UserRole.ADMIN]


class TokenLimitUpdate(BaseModel):
    token_limit: int = Field(ge=0)