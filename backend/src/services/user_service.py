from typing import Optional
from passlib.context import CryptContext

from src.repositories.user_repo import UserRepository
from src.repositories.token_usage_event_repo import TokenUsageEventRepository
from src.db.models.users import User

import logging

logger = logging.getLogger(__name__)

class UserService:
    
    _pwd_context = CryptContext(schemes = ['bcrypt'], deprecated = ['auto'])
    
    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: TokenUsageEventRepository
    ):
        self.user_repo = user_repo
        self.token_repo = token_repo
        
        
    async def create_user(
        self,
        username: str,
        email: str,
        password: str
    ) -> User:
        
        # Check username uniqueness
        existing_user = await self.user_repo.get_by_username(username)
        if existing_user:
            logger.warning("signup_rejected_username_taken: %s", username)
            raise ValueError(f"Username '{username}' already exists")
        
        # Check email uniqueness
        existing_email = await self.user_repo.get_by_email(email)
        if existing_email:
            logger.warning("signup_rejected_email_taken: %s", email)
            raise ValueError(f"Email '{email}' already registered")
        
        self._validate_password(password)
        
        password_hash = self._pwd_context.hash(password)
        
        user = await self.user_repo.create(
            username = username,
            email = email,
            password_hash = password_hash
        )
        
        logger.info("user_created: user_id=%s username=%s", user.id, username)
        
        return user
    
    async def authenticate_user(
        self,
        email: str,
        password: str
    ) -> Optional[User]:
        
        # Get user by email
        user = await self.user_repo.get_by_email(email)
        
        if not user:
            logger.warning('login_failed_unknown_email')
            return None
        
        # Verify password
        if not self._pwd_context.verify(password, user.password_hash):
            logger.warning("login_failed_bad_password: %s", user.id)
            return None
        
        logger.info('login_succeeded', user.id)
        
        return user
    
    async def check_token_limit(self, user: User) -> bool:
        
        return await self.token_repo.is_limit_exceeded(user)
    
    async def report_token_usage(self, user: User, tokens_used: int, agent_id: int | None = None) -> None:
        
        await self.token_repo.report_usage(
            user = user,
            tokens_used = tokens_used,
            agent_id = agent_id
        )
        logger.info("token_usage_reported: user=%s tokens=%s", user.id, tokens_used)
        
    async def get_user(self, user_id: int) -> User:
         
        user = await self.user_repo.get_by_id(user_id)
        
        if not user:
            logger.warning("user_not_found: %s", user_id)
            raise ValueError(f"User {user_id} not found")
        
        return user
    
    async def update_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        email: Optional[str] = None
    ) -> User:
        
        user = await self.get_user(user_id)
        
        kwargs = {}
        
        if username and username != user.username:
            existing = await self.user_repo.get_by_username(username)
            if existing and existing.id != user_id:
                raise ValueError(f"Username '{username}' already exists")
            kwargs["username"] = username
            
        if email and email != user.email:
            existing = await self.user_repo.get_by_email(email)
            if existing and existing.id != user_id:
                raise ValueError(f"Email '{email}' already registered")
            kwargs["email"] = email
        
        if kwargs:
            user = await self.user_repo.update(user, **kwargs)
        
        logger.info("user_updated: %s", user_id)
        
        return user
    
    async def change_password(
        self,
        user_id: int,
        old_password: str,
        new_password: str
    ) -> bool:
        
        user = await self.get_user(user_id)
        
        if not self._pwd_context.verify(old_password, user.password_hash):
            logger.warning("change_password_failed_wrong_current: %s", user_id)
            raise ValueError("Incorrect current password")
        
        self._validate_password(new_password) 
        
        # Hash new password
        new_password_hash = self._pwd_context.hash(new_password)
        
        await self.user_repo.update_password(user, new_password_hash)
        
        logger.info('password_changed', user_id)
        
        return True
    
    async def delete_user(self, user_id: int) -> None:
        
        # Check user exists
        user = await self.get_user(user_id)
        
        # Delete user (cascade deletes images and detections)
        success = await self.user_repo.delete(user)
        
        logger.info('user_deleted', user_id)
    
    def _validate_password(self, password: str) -> None:
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        
        if not any(c.isupper() for c in password):
            raise ValueError("Password must contain at least one uppercase letter")
        
        if not any(c.islower() for c in password):
            raise ValueError("Password must contain at least one lowercase letter")
        
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one digit")