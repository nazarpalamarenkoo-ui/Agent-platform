import logging
import re

from src.knowledge.acquisition.judge.exceptions import (
    JudgeClientError,
    JudgeParseError,
    JudgeValidationError,
)
from src.knowledge.acquisition.judge.judge_llm_client import JudgeLLMClient
from src.knowledge.acquisition.judge.models import JudgeItem, JudgeSource, TrustBreakdown
from src.knowledge.acquisition.judge.parse import parse
from src.knowledge.acquisition.judge.prompts import (
    DOCUMENT_BLOCK_TEMPLATE,
    JUDGE_SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from src.knowledge.documents_schema.document_candidate import DocumentCandidate

logger = logging.getLogger(__name__)


class LLMJudge:

    def __init__(
        self,
        client: JudgeLLMClient,
        batch_size: int = 3,
        max_retries: int = 1,
        temperatures: tuple[float, ...] = (0.1, 0.6),
        max_title_chars: int = 200,
        max_snippet_chars: int = 300,
        max_headings: int = 8,
        max_heading_chars: int = 80,
        max_first_page_chars: int = 800,
    ):
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if not temperatures:
            raise ValueError("temperatures must not be empty")

        self.client = client
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.temperatures = temperatures
        self.max_title_chars = max_title_chars
        self.max_snippet_chars = max_snippet_chars
        self.max_headings = max_headings
        self.max_heading_chars = max_heading_chars
        self.max_first_page_chars = max_first_page_chars

    async def evaluate(self, documents: list[DocumentCandidate]) -> list[JudgeSource]:
        if not documents:
            return []

        results: list[JudgeSource] = []

        for i in range(0, len(documents), self.batch_size):
            batch = documents[i:i + self.batch_size]
            results.extend(await self._evaluate_batch(batch))

        return results

    async def _evaluate_batch(self, batch: list[DocumentCandidate]) -> list[JudgeSource]:
        prompt = self._build_prompt(batch)
        keys = [doc.key for doc in batch]
        last_error = "unknown error"

        for attempt in range(1 + self.max_retries):
            temperature = self.temperatures[min(attempt, len(self.temperatures) - 1)]

            try:
                raw = await self.client.complete_json(
                    JUDGE_SYSTEM_PROMPT, prompt, temperature
                )
                items = parse(raw, keys)
            except JudgeClientError as e:
                logger.warning("Judge server error, batch of %d skipped: %s", len(batch), e)
                return self._fallback(batch, f"judge server unavailable: {e}")
            except (JudgeParseError, JudgeValidationError) as e:
                last_error = str(e)
                logger.warning(
                    "Judge attempt %d/%d failed: %s",
                    attempt + 1,
                    1 + self.max_retries,
                    e,
                )
                continue

            judge_map: dict[str, JudgeItem] = {item.key: item for item in items}

            return [
                JudgeSource(
                    key=doc.key,
                    url=doc.url,
                    title=doc.title,
                    trust=judge_map[doc.key].trust,
                    document_category=judge_map[doc.key].document_category,
                    reason=judge_map[doc.key].reason,
                )
                for doc in batch
            ]

        return self._fallback(batch, f"invalid response after retries: {last_error}")

    def _build_prompt(self, batch: list[DocumentCandidate]) -> str:
        doc_blocks = []

        for doc in batch:
            headings = [
                self._clean(h, self.max_heading_chars)
                for h in doc.headings[:self.max_headings]
                if h
            ]
            headings_text = " | ".join(headings) if headings else "(none)"

            doc_block = DOCUMENT_BLOCK_TEMPLATE.format(
                key=doc.key,
                title=self._clean(doc.title, self.max_title_chars),
                domain=self._clean(doc.domain, self.max_title_chars),
                snippet=self._clean(doc.snippet, self.max_snippet_chars),
                headings=headings_text,
                first_page=self._clean(doc.first_page, self.max_first_page_chars) or "(empty)",
            )
            doc_blocks.append(doc_block)

        keys = ", ".join(f'"{doc.key}"' for doc in batch)

        return USER_PROMPT_TEMPLATE.format(
            count=len(batch),
            keys=keys,
            documents="\n\n".join(doc_blocks),
        )

    def _clean(self, text: str, limit: int) -> str:
        if not text:
            return ""

        text = re.sub(r"</?\s*document\b[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()

        return text[:limit]

    def _fallback(self, batch: list[DocumentCandidate], reason: str) -> list[JudgeSource]:
        logger.warning("Judge fallback for %d documents: %s", len(batch), reason)

        return [
            JudgeSource(
                key=doc.key,
                url=doc.url,
                title=doc.title,
                trust=TrustBreakdown(
                    educational=0.0,
                    implementation=0.0,
                    authority=0.0,
                ),
                document_category="judge_error",
                reason=reason,
            )
            for doc in batch
        ]