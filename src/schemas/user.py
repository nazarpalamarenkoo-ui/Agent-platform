from pydantic import BaseModel, EmailStr

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
    tokens_used: int
    token_limit: int
    model_config = {"from_attributes": True}
    