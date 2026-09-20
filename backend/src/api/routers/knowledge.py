from fastapi import APIRouter, Depends, HTTPException, status

from src.dependencies import get_knowledge_service
from src.services.knowledge_service import KnowledgeService
from src.schemas.knowledge import (
    IngestFileRequest,
    IngestWebRequest,
    SearchRequest,
    SearchResultResponse,
)
from src.schemas.document import DocumentRead
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/ingest/file", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def ingest_file(
    body: IngestFileRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    try:
        document = await service.ingest_file(
            source=body.source,
            document_type=body.document_type,
            knowledge_type=body.knowledge_type,
            knowledge_pack_id=body.knowledge_pack_id,
        )
        return DocumentRead.model_validate(document)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/ingest/web", response_model=list[DocumentRead], status_code=status.HTTP_201_CREATED)
async def ingest_from_web(
    body: IngestWebRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
):
    try:
        documents = await service.ingest_from_web(
            query=body.query,
            limit=body.limit,
            document_type=body.document_type,
            knowledge_type=body.knowledge_type,
            knowledge_pack_id=body.knowledge_pack_id,
        )
        return [DocumentRead.model_validate(doc) for doc in documents]
    except Exception as e:
        logger.exception("ingest_from_web failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/search", response_model=list[SearchResultResponse])
async def search(
    body: SearchRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
):
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))