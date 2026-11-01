import logging

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.auth.auth import get_current_user, require_admin
from src.db.models.background_jobs import JobType
from src.db.models.users import User
from src.dependencies import (
    get_arq_pool,
    get_background_job_repo,
    get_config_bundle_service,
    get_knowledge_service,
    get_pack_repo,
)
from src.knowledge.documents_schema.corpus_build_result import CorpusBuilderResult
from src.repositories.background_job_repo import BackgroundJobRepository
from src.repositories.knowledge_pack_repo import KnowledgePackRepository
from src.schemas.knowledge import (
    AgenticEvidenceResponse,
    EvaluationResponse,
    IngestFileRequest,
    IngestWebRequest,
    IterationResponse,
    JobCreatedResponse,
    JobStatusResponse,
    SearchAgenticRequest,
    SearchAgenticResponse,
    SearchRequest,
    SearchResultResponse,
)
from src.services.config_bundle_service import ConfigBundleService
from src.services.errors import NotFoundError
from src.services.knowledge_service import KnowledgeService
from src.worker.queues import INGESTION_QUEUE

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(get_current_user)],
)


async def _ensure_bundle_access(
    actor: User,
    config_bundle_id: int | None,
    bundle_service: ConfigBundleService,
) -> None:
    if config_bundle_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="config_bundle_id is required")
    if actor.is_admin:
        return
    try:
        await bundle_service.get_bundle(config_bundle_id, actor.id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config bundle not found")


@router.post(
    "/ingest/file",
    response_model=CorpusBuilderResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def ingest_file(
    body: IngestFileRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    try:
        return await service.ingest_file(
            source=body.source,
            document_type=body.document_type,
            knowledge_type=body.knowledge_type,
            knowledge_pack_id=body.knowledge_pack_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/ingest/web",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
)
async def ingest_from_web(
    body: IngestWebRequest,
    actor: User = Depends(get_current_user),
    pack_repo: KnowledgePackRepository = Depends(get_pack_repo),
    job_repo: BackgroundJobRepository = Depends(get_background_job_repo),
    arq_pool: ArqRedis = Depends(get_arq_pool),
):
    # Раніше "pack не існує" приходило як ValueError з пайплайну (400).
    # Тепер це сталося б у воркері й стало б failed-job, тому перевіряємо одразу.
    if await pack_repo.get_active(body.knowledge_pack_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Knowledge pack id={body.knowledge_pack_id} does not exist or is archived",
        )

    # query, document_type, knowledge_type, knowledge_pack_id
    payload = body.model_dump(mode="json")
    job = await job_repo.create(
        job_type=JobType.DISCOVERY_INGEST, user_id=actor.id, payload=payload
    )
    try:
        enqueued = await arq_pool.enqueue_job(
            "run_discovery_ingest",
            job.id,
            **payload,
            _job_id=f"discovery_ingest:{job.id}",
            _queue_name=INGESTION_QUEUE,
        )
    except Exception as exc:
        logger.exception("Failed to enqueue job %d", job.id)
        await job_repo.mark_failed(job.id, f"Enqueue failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Queue unavailable"
        )
    if enqueued is None:  # такий _job_id уже існує в Redis
        await job_repo.mark_failed(job.id, "Duplicate arq job id")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job already enqueued")

    return JobCreatedResponse(job_id=job.id, status=job.status)


@router.get(
    "/ingest/jobs/{job_id}",
    response_model=JobStatusResponse,
    dependencies=[Depends(require_admin)],
)
async def get_ingest_job(
    job_id: int,
    job_repo: BackgroundJobRepository = Depends(get_background_job_repo),
):
    job = await job_repo.get(job_id)
    if job is None or job.job_type != JobType.DISCOVERY_INGEST.value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/search", response_model=list[SearchResultResponse])
async def search(
    body: SearchRequest,
    actor: User = Depends(get_current_user),
    service: KnowledgeService = Depends(get_knowledge_service),
    bundle_service: ConfigBundleService = Depends(get_config_bundle_service),
):
    await _ensure_bundle_access(actor, body.config_bundle_id, bundle_service)
    try:
        results = await service.search(
            query=body.query,
            limit=body.limit,
            top_n=body.top_n,
            k=body.k,
            config_bundle_id=body.config_bundle_id,
        )
        return [
            SearchResultResponse(id=r.id, score=r.score, payload=r.payload)
            for r in results
        ]
    except ValueError as e:
        logger.exception("search failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/search/agentic", response_model=SearchAgenticResponse)
async def search_agentic(
    body: SearchAgenticRequest,
    actor: User = Depends(get_current_user),
    service: KnowledgeService = Depends(get_knowledge_service),
    bundle_service: ConfigBundleService = Depends(get_config_bundle_service),
):
    await _ensure_bundle_access(actor, body.config_bundle_id, bundle_service)
    try:
        context = await service.search_agentic(
            query=body.query,
            config_bundle_id=body.config_bundle_id,
        )

        if context is None:
            return SearchAgenticResponse(
                initial_subqueries=[],
                reasoning="",
                evidence=[],
                iterations=[],
                degraded_to_hybrid=False,
            )

        degraded = len(context.iterations) == 0

        return SearchAgenticResponse(
            initial_subqueries=context.plan.subqueries,
            reasoning=context.plan.reasoning,
            evidence=[
                AgenticEvidenceResponse(
                    query=ev.query,
                    chunk_id=ev.chunk_id,
                    score=ev.score,
                    text=ev.text,
                    metadata=ev.metadata,
                )
                for ev in context.evidence
            ],
            iterations=[
                IterationResponse(
                    iteration=record.iteration,
                    subqueries=record.subqueries,
                    new_evidence_count=record.new_evidence_count,
                    total_evidence_count=record.total_evidence_count,
                    evaluation=EvaluationResponse(
                        sufficient=record.evaluation.sufficient,
                        coverage=record.evaluation.coverage,
                        confidence=record.evaluation.confidence,
                        redundancy=record.evaluation.redundancy,
                        missing_topics=record.evaluation.missing_topics,
                        retry_queries=record.evaluation.retry_queries,
                    ),
                )
                for record in context.iterations
            ],
            degraded_to_hybrid=degraded,
        )
    except ValueError as e:
        logger.exception("search_agentic failed")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))