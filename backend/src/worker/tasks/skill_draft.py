from src.catalog.draft.models import DraftSpec, Snippet
from src.worker.tracked import run_tracked_job


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
        return result.model_dump(mode="json")

    return await run_tracked_job(ctx["job_repo"], job_id, work)