import logging

from fastapi import APIRouter, Depends

from src.api.auth.auth import get_current_user
from src.api.routers.rate_limit import enforce_hint_rate_limit
from src.api.routers.errors import hint_to_http, to_http
from src.catalog.hint.catalog_hint_service import CatalogHintService
from src.catalog.hint.exceptions import HintError
from src.db.models.users import User
from src.dependencies import get_catalog_hint_service
from src.schemas.catalog import HintRequest, HintResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/catalog",
    tags=["catalog"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/hint",
    response_model=HintResponse,
    dependencies=[Depends(enforce_hint_rate_limit)],
)
async def propose_hint(
    body: HintRequest,
    actor: User = Depends(get_current_user),
    service: CatalogHintService = Depends(get_catalog_hint_service),
):
    try:
        return await service.propose(viewer_id=actor.id, intent=body.intent)
    except HintError as e:
        logger.warning("Hint failed for user %s: %s", actor.id, e)
        raise hint_to_http(e)
    except ValueError as e:
        raise to_http(e)