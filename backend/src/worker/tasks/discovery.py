import logging

from src.db.enums.document_type import DocumentType
from src.db.enums.knowledge_types import KnowledgeType
from src.worker.tracked import run_tracked_job

logger = logging.getLogger(__name__)


async def run_discovery_ingest(
    ctx: dict,
    job_id: int,
    query: str,
    document_type: str,
    knowledge_type: str,
    knowledge_pack_id: int,
) -> dict:

    async def work():
        return await ctx["corpus_builder"].build_from_search(
            query=query,
            knowledge_pack_id=knowledge_pack_id,
            document_type=DocumentType(document_type),
            knowledge_type=KnowledgeType(knowledge_type),
        )

    return await run_tracked_job(ctx["job_repo"], job_id, work)