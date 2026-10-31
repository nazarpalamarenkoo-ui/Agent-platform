from src.db.models.users import User
from src.services.errors import ForbiddenError


def require_admin(actor: User) -> None:
    if not actor.is_admin:
        raise ForbiddenError("Admin access required")