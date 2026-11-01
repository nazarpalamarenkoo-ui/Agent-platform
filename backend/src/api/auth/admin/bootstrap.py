import logging

from sqlalchemy.exc import IntegrityError

from src.config import settings
from src.db.db_connection import AsyncSessionLocal
from src.repositories.token_usage_event_repo import TokenUsageEventRepository
from src.repositories.user_repo import UserRepository
from src.services.user_service import UserService

logger = logging.getLogger(__name__)


async def ensure_super_admin() -> None:
    email = getattr(settings, "SUPER_ADMIN_EMAIL", None)
    username = getattr(settings, "SUPER_ADMIN_USERNAME", None)
    password = getattr(settings, "SUPER_ADMIN_PASSWORD", None)

    async with AsyncSessionLocal() as session:
        service = UserService(
            user_repo=UserRepository(session),
            token_repo=TokenUsageEventRepository(session),
        )

        if await service.user_repo.get_super_admin() is not None:
            return

        if not (email and username and password):
            logger.warning("super_admin_missing_and_not_configured")
            return

        try:
            await service.ensure_super_admin(username, email, password)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.info("super_admin_created_concurrently")