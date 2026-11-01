from pydantic import BaseModel, EmailStr
from typing import Optional


class TokenData(BaseModel):
    username: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


class SignUpArgs(BaseModel):
    email: EmailStr
    password: str
    username: str


class SignInArgs(BaseModel):
    email: EmailStr
    password: str


class PendingSignup(BaseModel):
    email: EmailStr
    username: str
    password_hash: str


class ResetPasswordArgs(BaseModel):
    token: str
    new_password: str