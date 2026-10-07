import json
import logging

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)

from src.knowledge.acquisition.judge.exceptions import (
    JudgeClientError,
    JudgeParseError,
)
from src.knowledge.acquisition.judge.models import JudgeResponse

logger = logging.getLogger(__name__)


class JudgeLLMClient:

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout: float = 120.0,
        max_tokens: int = 1500,
        use_json_schema: bool = False,
    ):
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,
        )
        self.model = model
        self.max_tokens = max_tokens
        self.use_json_schema = use_json_schema

    async def complete_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
    ) -> dict:
        kwargs = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }

        if self.use_json_schema:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "judge_response",
                    "schema": JudgeResponse.model_json_schema(),
                },
            }

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except (APIConnectionError, APITimeoutError) as e:
            raise JudgeClientError(f"Judge server unavailable or timed out: {e}") from e
        except APIStatusError as e:
            raise JudgeClientError(f"Judge server returned an error: {e}") from e

        choice = response.choices[0]

        if choice.finish_reason == "length":
            raise JudgeParseError("Response was cut off by max_tokens, JSON is incomplete")

        raw = choice.message.content
        if not raw:
            raise JudgeParseError("Empty response from the model")

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]

        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError as e:
            logger.error("Unable to parse JSON from the model: %s", raw[:200])
            raise JudgeParseError("Invalid JSON in the model response") from e