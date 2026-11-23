import logging

from src.catalog.draft.models import DraftSpec, Snippet
from src.rag.retrieval.agentic.llm_client import track_token_usage
from src.worker.tracked import run_tracked_job

logger = logging.getLogger(__name__)


def _snippet(s: dict) -> Snippet:
    return Snippet.from_dict(s)


async def run_skill_draft(
    ctx: dict,
    job_id: int,
    intent: str,
    skill_name: str | None = None,
    description: str | None = None,
    source_text: str | None = None,
    snippets: list[dict] | None = None,
    retrieval_warnings: list[str] | None = None,
) -> dict:
    async def work():
        with track_token_usage() as usage:
            try:
                result = await ctx["draft_generator"].generate(
                    DraftSpec(
                        intent=intent,
                        skill_name=skill_name,
                        description=description,
                        source_text=source_text,
                        snippets=tuple(_snippet(s) for s in snippets or []),
                        warnings=tuple(retrieval_warnings or []),
                    )
                )
            finally:
                token_repo = ctx.get("token_repo")
                job_repo = ctx.get("job_repo")
                if token_repo is not None and job_repo is not None and usage.total_tokens > 0:
                    try:
                        job = await job_repo.get(job_id)
                        user_id = getattr(job, "user_id", None)
                        if user_id is not None:
                            await token_repo.report_usage_by_user_id(
                                user_id=user_id,
                                tokens_used=usage.total_tokens,
                            )
                    except Exception:
                        logger.warning(
                            "Failed to record draft token usage for job %s", job_id, exc_info=True
                        )
        return result.model_dump(mode="json")

    return await run_tracked_job(ctx["job_repo"], job_id, work)