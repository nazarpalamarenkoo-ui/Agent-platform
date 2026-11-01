from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from src.api.auth.auth import get_current_user
from src.api.routers.errors import to_http
from src.api.routers.rate_limit import enforce_draft_rate_limit
from src.db.models.users import User
from src.dependencies import (
    get_skill_access_log_repo,
    get_skill_draft_service,
    get_user_skill_service,
)
from src.repositories.skill_access_log_repo import SkillAccessLogRepository
from src.schemas.admin_skills import AccessLogEntry
from src.schemas.skill_drafts import (
    AttachPacksRequest,
    AttachPacksResponse,
    PackSuggestion,
    SkillDraftConfirm,
    SkillDraftJobResponse,
    SkillDraftRequest,
    SkillDraftStatus,
    SuggestPacksRequest,
)
from src.schemas.user_skills import (
    MySkillCreate,
    MySkillImport,
    MySkillRead,
    MySkillSummary,
    MySkillUpdate,
)
from src.services.skill_draft_service import DraftQueueError, SkillDraftService
from src.services.user_skill_service import UserSkillService

router = APIRouter(
    prefix="/my/skills",
    tags=["my-skills"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[MySkillSummary])
async def list_my_skills(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_archived: bool = False,
    actor: User = Depends(get_current_user),
    service: UserSkillService = Depends(get_user_skill_service),
) -> list[MySkillSummary]:
    skills = await service.list_skills(
        actor, limit=limit, offset=offset, include_archived=include_archived
    )
    return [MySkillSummary.model_validate(s) for s in skills]


@router.post("", response_model=MySkillRead, status_code=status.HTTP_201_CREATED)
async def create_my_skill(
    body: MySkillCreate,
    actor: User = Depends(get_current_user),
    service: UserSkillService = Depends(get_user_skill_service),
) -> MySkillRead:
    try:
        skill = await service.create_skill(
            actor, body.skill_name, body.description, body.content, body.domain_ids
        )
        return MySkillRead.model_validate(skill)
    except ValueError as e:
        raise to_http(e)


@router.post("/import", response_model=MySkillRead, status_code=status.HTTP_201_CREATED)
async def import_my_skill(
    body: MySkillImport,
    actor: User = Depends(get_current_user),
    service: UserSkillService = Depends(get_user_skill_service),
) -> MySkillRead:
    try:
        skill = await service.import_markdown(
            actor, body.markdown, body.skill_name, body.description, body.domain_ids
        )
        return MySkillRead.model_validate(skill)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/drafts",
    response_model=SkillDraftJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_draft_rate_limit)],
)
async def request_skill_draft(
    body: SkillDraftRequest,
    actor: User = Depends(get_current_user),
    service: SkillDraftService = Depends(get_skill_draft_service),
):
    try:
        job_id, job_status = await service.request_draft(actor, body)
    except DraftQueueError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Queue unavailable")
    except ValueError as e:
        raise to_http(e)
    return SkillDraftJobResponse(job_id=job_id, status=job_status)


@router.get("/drafts/{job_id}", response_model=SkillDraftStatus)
async def get_skill_draft(
    job_id: int,
    actor: User = Depends(get_current_user),
    service: SkillDraftService = Depends(get_skill_draft_service),
):
    try:
        return await service.get_status(actor, job_id)
    except ValueError as e:
        raise to_http(e)


@router.post(
    "/drafts/{job_id}/confirm",
    response_model=MySkillRead,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_skill_draft(
    job_id: int,
    body: SkillDraftConfirm,
    actor: User = Depends(get_current_user),
    service: SkillDraftService = Depends(get_skill_draft_service),
):
    try:
        return MySkillRead.model_validate(await service.confirm(actor, job_id, body))
    except ValueError as e:
        raise to_http(e)


@router.get("/{skill_id}", response_model=MySkillRead)
async def get_my_skill(
    skill_id: int,
    actor: User = Depends(get_current_user),
    service: UserSkillService = Depends(get_user_skill_service),
) -> MySkillRead:
    try:
        return MySkillRead.model_validate(await service.get_skill(actor, skill_id))
    except ValueError as e:
        raise to_http(e)


@router.put("/{skill_id}", response_model=MySkillRead)
async def update_my_skill(
    skill_id: int,
    body: MySkillUpdate,
    actor: User = Depends(get_current_user),
    service: UserSkillService = Depends(get_user_skill_service),
) -> MySkillRead:
    try:
        skill = await service.update_skill(
            actor,
            skill_id,
            skill_name=body.skill_name,
            description=body.description,
            content=body.content,
        )
        return MySkillRead.model_validate(skill)
    except ValueError as e:
        raise to_http(e)


@router.post("/{skill_id}/archive", response_model=MySkillRead)
async def archive_my_skill(
    skill_id: int,
    actor: User = Depends(get_current_user),
    service: UserSkillService = Depends(get_user_skill_service),
) -> MySkillRead:
    try:
        return MySkillRead.model_validate(await service.archive_skill(actor, skill_id))
    except ValueError as e:
        raise to_http(e)


@router.post("/{skill_id}/restore", response_model=MySkillRead)
async def restore_my_skill(
    skill_id: int,
    actor: User = Depends(get_current_user),
    service: UserSkillService = Depends(get_user_skill_service),
) -> MySkillRead:
    try:
        return MySkillRead.model_validate(await service.restore_skill(actor, skill_id))
    except ValueError as e:
        raise to_http(e)


@router.get("/{skill_id}/download")
async def download_my_skill(
    skill_id: int,
    actor: User = Depends(get_current_user),
    service: UserSkillService = Depends(get_user_skill_service),
) -> Response:
    try:
        text = await service.export_markdown(actor, skill_id)
    except ValueError as e:
        raise to_http(e)
    return Response(
        content=text,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="SKILL.md"'},
    )