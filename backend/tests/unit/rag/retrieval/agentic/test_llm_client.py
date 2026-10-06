from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIError, RateLimitError

from src.rag.retrieval.agentic.exceptions import (
    LLMClientError,
    LLMParseError,
    LLMRateLimitError,
)
from src.rag.retrieval.agentic.llm_client import (
    DEFAULT_MODEL,
    GROQ_BASE_URL,
    LLMClient,
)

MODULE = "src.rag.retrieval.agentic.llm_client"


def make_rate_limit_error():
    request = httpx.Request("POST", "http://test")
    response = httpx.Response(429, request=request)
    return RateLimitError("rate limited", response=response, body=None)


def make_api_error():
    return APIError("boom", request=httpx.Request("POST", "http://test"), body=None)


def make_response(content):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    return resp


@pytest.fixture
def mock_openai_cls():
    with patch(f"{MODULE}.AsyncOpenAI") as cls:
        cls.return_value.chat.completions.create = AsyncMock(
            return_value=make_response("hello")
        )
        yield cls


@pytest.fixture
def mock_sleep():
    with patch(f"{MODULE}.asyncio.sleep", new_callable=AsyncMock) as sleep:
        yield sleep


@pytest.fixture
def client(mock_openai_cls):
    return LLMClient(api_key="key")


@pytest.fixture
def create(client):
    return client._client.chat.completions.create


class TestInit:

    def test_creates_async_openai_with_key_and_default_base_url(self, mock_openai_cls):
        LLMClient(api_key="secret")
        mock_openai_cls.assert_called_once_with(api_key="secret", base_url=GROQ_BASE_URL)

    def test_custom_base_url(self, mock_openai_cls):
        LLMClient(api_key="k", base_url="http://local")
        mock_openai_cls.assert_called_once_with(api_key="k", base_url="http://local")

    def test_defaults(self, client):
        assert client.model == DEFAULT_MODEL
        assert client.max_retries == 3
        assert client.retry_delay == 2.0

    def test_custom_settings(self, mock_openai_cls):
        c = LLMClient(api_key="k", model="m", max_retries=5, retry_delay=0.5)
        assert (c.model, c.max_retries, c.retry_delay) == ("m", 5, 0.5)


class TestComplete:

    async def test_returns_message_content(self, client):
        assert await client.complete("hi") == "hello"

    async def test_sends_system_and_user_messages(self, client, create):
        await client.complete("user text", system="sys text")

        kwargs = create.call_args.kwargs
        assert kwargs["messages"] == [
            {"role": "system", "content": "sys text"},
            {"role": "user", "content": "user text"},
        ]

    async def test_omits_system_message_when_none(self, client, create):
        await client.complete("user text")

        assert create.call_args.kwargs["messages"] == [
            {"role": "user", "content": "user text"}
        ]

    async def test_passes_model_and_max_tokens(self, mock_openai_cls):
        c = LLMClient(api_key="k", model="custom-model")
        create = c._client.chat.completions.create

        await c.complete("hi")

        assert create.call_args.kwargs["model"] == "custom-model"
        assert create.call_args.kwargs["max_tokens"] == 2000

    async def test_single_call_on_success(self, client, create, mock_sleep):
        await client.complete("hi")

        create.assert_awaited_once()
        mock_sleep.assert_not_called()


class TestCompleteRetries:

    async def test_retries_after_rate_limit_then_succeeds(self, client, create, mock_sleep):
        create.side_effect = [make_rate_limit_error(), make_response("ok")]

        result = await client.complete("hi")

        assert result == "ok"
        assert create.await_count == 2
        mock_sleep.assert_awaited_once_with(2.0)

    async def test_exponential_backoff_delays(self, client, create, mock_sleep):
        create.side_effect = [
            make_rate_limit_error(),
            make_rate_limit_error(),
            make_response("ok"),
        ]

        await client.complete("hi")

        assert [c.args[0] for c in mock_sleep.await_args_list] == [2.0, 4.0]

    async def test_backoff_uses_custom_retry_delay(self, mock_openai_cls, mock_sleep):
        c = LLMClient(api_key="k", retry_delay=0.5)
        c._client.chat.completions.create = AsyncMock(
            side_effect=[make_rate_limit_error(), make_rate_limit_error(), make_response("ok")]
        )

        await c.complete("hi")

        assert [x.args[0] for x in mock_sleep.await_args_list] == [0.5, 1.0]

    async def test_raises_rate_limit_error_after_all_attempts(self, client, create, mock_sleep):
        create.side_effect = make_rate_limit_error()

        with pytest.raises(LLMRateLimitError):
            await client.complete("hi")

        assert create.await_count == 3
        assert mock_sleep.await_count == 2  # без сну після останньої спроби

    async def test_rate_limit_error_chained_from_original(self, client, create, mock_sleep):
        create.side_effect = make_rate_limit_error()

        with pytest.raises(LLMRateLimitError) as exc_info:
            await client.complete("hi")

        assert isinstance(exc_info.value.__cause__, RateLimitError)

    async def test_respects_custom_max_retries(self, mock_openai_cls, mock_sleep):
        c = LLMClient(api_key="k", max_retries=5)
        c._client.chat.completions.create = AsyncMock(side_effect=make_rate_limit_error())

        with pytest.raises(LLMRateLimitError):
            await c.complete("hi")

        assert c._client.chat.completions.create.await_count == 5

    async def test_generic_api_error_not_retried(self, client, create, mock_sleep):
        create.side_effect = make_api_error()

        with pytest.raises(LLMClientError):
            await client.complete("hi")

        create.assert_awaited_once()
        mock_sleep.assert_not_called()

    async def test_api_error_chained_from_original(self, client, create):
        create.side_effect = make_api_error()

        with pytest.raises(LLMClientError) as exc_info:
            await client.complete("hi")

        assert isinstance(exc_info.value.__cause__, APIError)

    async def test_api_error_after_rate_limit_raises_client_error(self, client, create, mock_sleep):
        create.side_effect = [make_rate_limit_error(), make_api_error()]

        with pytest.raises(LLMClientError):
            await client.complete("hi")

    async def test_rate_limit_error_is_not_client_error(self, client, create, mock_sleep):
        create.side_effect = make_rate_limit_error()

        with pytest.raises(LLMRateLimitError) as exc_info:
            await client.complete("hi")

        assert not isinstance(exc_info.value, LLMClientError)

    async def test_zero_retries_raises_exhausted_error(self, mock_openai_cls):
        c = LLMClient(api_key="k", max_retries=0)

        with pytest.raises(LLMClientError, match="exhausted"):
            await c.complete("hi")

        c._client.chat.completions.create.assert_not_called()

    async def test_unexpected_exception_propagates(self, client, create):
        create.side_effect = ValueError("unexpected")

        with pytest.raises(ValueError):
            await client.complete("hi")


class TestCompleteJson:

    async def _run(self, client, raw):
        client.complete = AsyncMock(return_value=raw)
        return await client.complete_json("prompt", system="sys")

    async def test_parses_plain_json(self, client):
        assert await self._run(client, '{"a": 1}') == {"a": 1}

    async def test_parses_json_with_surrounding_whitespace(self, client):
        assert await self._run(client, '  \n{"a": 1}\n  ') == {"a": 1}

    async def test_parses_json_fenced_with_language_tag(self, client):
        assert await self._run(client, '```json\n{"a": 1}\n```') == {"a": 1}

    async def test_parses_json_fenced_without_language_tag(self, client):
        assert await self._run(client, '```\n{"a": 1}\n```') == {"a": 1}

    async def test_parses_nested_structures(self, client):
        raw = '{"subqueries": ["x", "y"], "meta": {"n": 2}}'
        assert await self._run(client, raw) == {"subqueries": ["x", "y"], "meta": {"n": 2}}

    async def test_invalid_json_raises_parse_error(self, client):
        with pytest.raises(LLMParseError):
            await self._run(client, "not json at all")

    async def test_empty_response_raises_parse_error(self, client):
        with pytest.raises(LLMParseError):
            await self._run(client, "")

    async def test_bare_fence_raises_parse_error(self, client):
        with pytest.raises(LLMParseError):
            await self._run(client, "```")

    async def test_text_before_fence_raises_parse_error(self, client):
        with pytest.raises(LLMParseError):
            await self._run(client, 'Here you go: ```json\n{"a": 1}\n```')

    async def test_parse_error_chained_from_original(self, client):
        with pytest.raises(LLMParseError) as exc_info:
            await self._run(client, "nope")

        assert exc_info.value.__cause__ is not None

    async def test_passes_prompt_and_system_to_complete(self, client):
        client.complete = AsyncMock(return_value="{}")

        await client.complete_json("my prompt", system="my system")

        client.complete.assert_awaited_once_with(prompt="my prompt", system="my system")

    async def test_system_defaults_to_none(self, client):
        client.complete = AsyncMock(return_value="{}")

        await client.complete_json("p")

        client.complete.assert_awaited_once_with(prompt="p", system=None)

    async def test_propagates_rate_limit_error(self, client):
        client.complete = AsyncMock(side_effect=LLMRateLimitError("limit"))

        with pytest.raises(LLMRateLimitError):
            await client.complete_json("p")