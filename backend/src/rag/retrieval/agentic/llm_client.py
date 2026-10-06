import json
import asyncio
import logging
from openai import AsyncOpenAI, RateLimitError, APIError
from src.rag.retrieval.agentic.exceptions import LLMRateLimitError, LLMClientError, LLMParseError

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"

class LLMClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = GROQ_BASE_URL,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        max_tokens: int = 4000,
    ):
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.max_tokens = max_tokens

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                )
                choice = response.choices[0]
                if choice.finish_reason == "length":
                    # gpt-oss is a reasoning model: reasoning tokens count
                    # against max_tokens, so the JSON can get cut off.
                    logger.warning("LLM response truncated (finish_reason=length)")
                return choice.message.content or ""

            except RateLimitError as e:
                last_error = e
                logger.warning(
                    f"Rate limit hit (attempt {attempt + 1}/{self.max_retries})"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise LLMRateLimitError(
                        "The request limit for the LLM API has been reached"
                    ) from e

            except APIError as e:
                raise LLMClientError(f"LLM API error: {e}") from e

        raise LLMClientError("All attempts have been exhausted") from last_error

    async def complete_json(
        self,
        prompt: str,
        system: str | None = None,
    ) -> dict:
        raw = await self.complete(prompt=prompt, system=system)

        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            return json.loads(cleaned.strip())

        except (json.JSONDecodeError, IndexError) as e:
            logger.error(f"Unable to parse the JSON: {raw[:200]}")
            raise LLMParseError(
                f"Invalid JSON in the LLM response"
            ) from e