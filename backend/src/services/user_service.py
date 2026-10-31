from typing import Optional
from passlib.context import CryptContext

from src.repositories.user_repo import UserRepository
from src.repositories.token_usage_event_repo import TokenUsageEventRepository
from src.db.enums.user_role import UserRole
from src.db.models.users import User
from src.services.errors import ConflictError, ForbiddenError, NotFoundError

import logging

logger = logging.getLogger(__name__)


class UserService:

    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated=["auto"])

    def __init__(
        self,
        user_repo: UserRepository,
        token_repo: TokenUsageEventRepository,
    ):
        self.user_repo = user_repo
        self.token_repo = token_repo


    async def prepare_signup(self, username: str, email: str, password: str) -> str:
        await self._ensure_unique(username, email)
        self._validate_password(password)
        return self._pwd_context.hash(password)

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
    ) -> User:
        password_hash = await self.prepare_signup(username, email, password)
        return await self.create_user_from_hash(username, email, password_hash)

    async def create_user_from_hash(
        self,
        username: str,
        email: str,
        password_hash: str,
    ) -> User:
        await self._ensure_unique(username, email)

        user = await self.user_repo.create(
            username=username,
            email=email,
            password_hash=password_hash,
        )

        logger.info("user_created: user_id=%s username=%s", user.id, username)

        return user

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> Optional[User]:
        user = await self.user_repo.get_by_email(email)

        if not user:
            logger.warning("login_failed_unknown_email")
            return None

        if not self._pwd_context.verify(password, user.password_hash):
            logger.warning("login_failed_bad_password: %s", user.id)
            return None

        logger.info("login_succeeded: %s", user.id)

        return user


    async def check_token_limit(self, user: User) -> bool:
        return await self.token_repo.is_limit_exceeded(user)

    async def report_token_usage(self, user: User, tokens_used: int, agent_id: int | None = None) -> None:
        await self.token_repo.report_usage(
            user=user,
            tokens_used=tokens_used,
            agent_id=agent_id,
        )
        logger.info("token_usage_reported: user=%s tokens=%s", user.id, tokens_used)

    async def get_user(self, user_id: int) -> User:
        user = await self.user_repo.get_by_id(user_id)

        if not user:
            logger.warning("user_not_found: %s", user_id)
            raise ValueError(f"User {user_id} not found")

        return user

    async def get_user_for(self, actor: User, user_id: int) -> User:
        """Отримати користувача з урахуванням прав actor."""
        target = await self._get_target(user_id)
        self._ensure_can_manage(actor, target)
        return target

    async def update_user(
        self,
        actor: User,
        user_id: int,
        username: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        user = await self._get_target(user_id)
        self._ensure_can_manage(actor, user)

        kwargs = {}

        if username and username != user.username:
            existing = await self.user_repo.get_by_username(username)
            if existing and existing.id != user_id:
                raise ConflictError(f"Username '{username}' already exists")
            kwargs["username"] = username

        if email and email != user.email:
            existing = await self.user_repo.get_by_email(email)
            if existing and existing.id != user_id:
                raise ConflictError(f"Email '{email}' already registered")
            kwargs["email"] = email

        if kwargs:
            user = await self.user_repo.update(user, **kwargs)

        logger.info("user_updated: actor=%s target=%s", actor.id, user_id)

        return user

    async def change_password(
        self,
        user_id: int,
        old_password: str,
        new_password: str,
    ) -> bool:
        user = await self.get_user(user_id)

        if not self._pwd_context.verify(old_password, user.password_hash):
            logger.warning("change_password_failed_wrong_current: %s", user_id)
            raise ValueError("Incorrect current password")

        self._validate_password(new_password)

        await self.user_repo.update_password(user, self._pwd_context.hash(new_password))

        logger.info("password_changed: %s", user_id)

        return True

    async def reset_password(self, user_id: int, new_password: str) -> None:
        user = await self.get_user(user_id)

        self._validate_password(new_password)

        await self.user_repo.update_password(user, self._pwd_context.hash(new_password))

        logger.info("password_reset: %s", user_id)

    async def delete_user(self, actor: User, user_id: int) -> None:
        target = await self._get_target(user_id)

        if target.role == UserRole.SUPER_ADMIN:
            raise ForbiddenError("The super admin account cannot be deleted")

        self._ensure_can_manage(actor, target)

        await self.user_repo.delete(target)

        logger.info("user_deleted: actor=%s target=%s", actor.id, user_id)

    async def list_users(self, limit: int = 50, offset: int = 0) -> list[User]:
        return await self.user_repo.list_page(limit=limit, offset=offset)

    async def set_token_limit(self, actor: User, user_id: int, token_limit: int) -> User:
        target = await self._get_target(user_id)
        self._ensure_can_manage(actor, target)

        await self.user_repo.set_token_limit(target, token_limit)

        logger.info(
            "token_limit_changed: actor=%s target=%s limit=%s",
            actor.id, target.id, token_limit,
        )
        return target

    async def reset_usage(self, actor: User, user_id: int) -> User:
        target = await self._get_target(user_id)
        self._ensure_can_manage(actor, target)

        await self.user_repo.reset_usage(target)

        logger.info("usage_reset: actor=%s target=%s", actor.id, target.id)
        return target

    async def ensure_super_admin(self, username: str, email: str, password: str) -> User:
        existing = await self.user_repo.get_super_admin()
        if existing is not None:
            return existing

        user = await self.user_repo.get_by_email(email)
        if user is not None:
            await self.user_repo.set_role(user, UserRole.SUPER_ADMIN)
            logger.info("super_admin_promoted: user_id=%s", user.id)
            return user

        if await self.user_repo.get_by_username(username):
            raise ValueError(f"Username '{username}' already exists")

        self._validate_password(password)

        user = await self.user_repo.create(
            username=username,
            email=email,
            password_hash=self._pwd_context.hash(password),
            role=UserRole.SUPER_ADMIN,
        )
        logger.info("super_admin_created: user_id=%s", user.id)
        return user

    async def list_admins(self) -> list[User]:
        return await self.user_repo.list_by_roles([UserRole.ADMIN, UserRole.SUPER_ADMIN])

    async def set_role(self, actor: User, target_id: int, role: UserRole) -> User:
        if actor.role != UserRole.SUPER_ADMIN:
            raise ForbiddenError("Only the super admin can change roles")

        if role not in (UserRole.USER, UserRole.ADMIN):
            raise ValueError("Only the 'user' and 'admin' roles can be assigned")

        target = await self.user_repo.get_by_id(target_id)
        if target is None:
            raise NotFoundError("User not found")

        if target.id == actor.id:
            raise ConflictError("You cannot change your own role")

        if target.role == UserRole.SUPER_ADMIN:
            raise ForbiddenError("The role of the super admin cannot be changed")

        if target.role != role:
            await self.user_repo.set_role(target, role)
            logger.info("role_changed: actor=%s target=%s role=%s", actor.id, target.id, role.value)

        return target


    async def _get_target(self, user_id: int) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    @staticmethod
    def _ensure_can_manage(actor: User, target: User) -> None:
        if actor.id == target.id:
            return

        if not actor.is_admin:
            raise ForbiddenError("Forbidden")

        if target.is_admin and not actor.is_super_admin:
            raise ForbiddenError("Only the super admin can manage other admins")

    async def _ensure_unique(self, username: str, email: str) -> None:
        if await self.user_repo.get_by_username(username):
            logger.warning("signup_rejected_username_taken: %s", username)
            raise ValueError(f"Username '{username}' already exists")

        if await self.user_repo.get_by_email(email):
            logger.warning("signup_rejected_email_taken")
            raise ValueError(f"Email '{email}' already registered")

    def _validate_password(self, password: str) -> None:
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")

        if not any(c.isupper() for c in password):
            raise ValueError("Password must contain at least one uppercase letter")

        if not any(c.islower() for c in password):
            raise ValueError("Password must contain at least one lowercase letter")

        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one digit")