import logging
from typing import List
from pydantic import ValidationError
from src.rag.retrieval.agentic.exceptions import LLMParseError
from src.rag.retrieval.agentic.llm_client import LLMClient
from src.rag.retrieval.agentic.models import RetrievalEvaluation, RetrievalEvidence
from src.rag.retrieval.agentic.prompts import EVALUATOR_USER_TEMPLATE, EVALUATOR_SYSTEM

logger = logging.getLogger(__name__)


class LLMEvaluator:
    def __init__(self, llm_client: LLMClient, evidence_count: int = 8, max_chars: int = 1500):

        self.llm_client = llm_client
        self.evidence_count = evidence_count
        self.max_chars = max_chars

    def _format_evidence(self, evidences: List[RetrievalEvidence], count: int, max_chars: int):
        # The orchestrator already passes unique chunks ranked best-first
        # (weighted RRF). Do NOT re-sort by `score`: it is the fused score now,
        # and raw reranker scores of different subqueries are not comparable.
        # The score is also not shown to the LLM - tiny RRF numbers would be
        # read as "low confidence". Dedupe defensively, keep the given order.
        seen: set[str] = set()
        selected: list[RetrievalEvidence] = []
        for ev in evidences:
            if ev.chunk_id in seen:
                continue
            seen.add(ev.chunk_id)
            selected.append(ev)
            if len(selected) >= count:
                break

        lines = []
        for i, ev in enumerate(selected, 1):
            text_preview = (ev.text[:max_chars] + '...') if len(ev.text) > max_chars else ev.text
            lines.append(f"Evidence {i}: {text_preview}")
        return "\n\n".join(lines), len(selected)

    async def evaluate(
        self,
        query: str,
        evidences: List[RetrievalEvidence],
    ) -> RetrievalEvaluation:

        formatted_evidence, evidence_count = self._format_evidence(evidences, self.evidence_count, self.max_chars)

        prompt = EVALUATOR_USER_TEMPLATE.format(
            query=query,
            evidence_count=evidence_count,
            evidence_text=formatted_evidence,
        )

        try:
            response = await self.llm_client.complete_json(prompt=prompt, system=EVALUATOR_SYSTEM)

            return RetrievalEvaluation(
                coverage=response["coverage"],
                confidence=response["confidence"],
                redundancy=response["redundancy"],
                sufficient=response["sufficient"],
                missing_topics=response['missing_topics'],
                retry_queries=response['retry_queries']
            )

        except (LLMParseError, ValidationError, KeyError) as e:
            logger.warning(f"LLMEvaluator failed to parse response, using fallback: {e}")
            return RetrievalEvaluation(
                coverage=0.0,
                confidence=0.0,
                redundancy=0.0,
                sufficient=False,
                missing_topics=[],
                retry_queries=[]
            )