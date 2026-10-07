import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, APITimeoutError

from src.knowledge.acquisition.judge.exceptions import JudgeClientError, JudgeParseError
from src.knowledge.acquisition.judge.judge_llm_client import JudgeLLMClient

REQUEST = httpx.Request("POST", "http://judge.local/v1/chat/completions")


def make_completion(content, finish_reason="stop"):
    choice = SimpleNamespace(
        finish_reason=finish_reason,
        message=SimpleNamespace(content=content),
    )
    return SimpleNamespace(choices=[choice])


@pytest.fixture
def judge_client():
    client = JudgeLLMClient(base_url="http://judge.local/v1", model="test-model", max_tokens=500)
    client.client = MagicMock()
    client.client.chat.completions.create = AsyncMock(
        return_value=make_completion(json.dumps({"results": []}))
    )
    return client


def create_mock(judge_client):
    return judge_client.client.chat.completions.create


class TestRequest:

    @pytest.mark.asyncio
    async def test_sends_expected_parameters(self, judge_client):
        await judge_client.complete_json("SYS", "USER", temperature=0.3)

        kwargs = create_mock(judge_client).await_args.kwargs
        assert kwargs["model"] == "test-model"
        assert kwargs["temperature"] == 0.3
        assert kwargs["max_tokens"] == 500
        assert kwargs["messages"] == [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "USER"},
        ]

    @pytest.mark.asyncio
    async def test_default_temperature_is_zero(self, judge_client):
        await judge_client.complete_json("s", "u")

        assert create_mock(judge_client).await_args.kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_no_response_format_by_default(self, judge_client):
        await judge_client.complete_json("s", "u")

        assert "response_format" not in create_mock(judge_client).await_args.kwargs

    @pytest.mark.asyncio
    async def test_json_schema_mode_adds_response_format(self, judge_client):
        judge_client.use_json_schema = True

        await judge_client.complete_json("s", "u")

        response_format = create_mock(judge_client).await_args.kwargs["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["name"] == "judge_response"
        assert "results" in response_format["json_schema"]["schema"]["properties"]


class TestResponseParsing:

    @pytest.mark.asyncio
    async def test_returns_parsed_json(self, judge_client):
        create_mock(judge_client).return_value = make_completion('{"results": [{"key": "a"}]}')

        assert await judge_client.complete_json("s", "u") == {"results": [{"key": "a"}]}

    @pytest.mark.asyncio
    async def test_strips_json_code_fence(self, judge_client):
        create_mock(judge_client).return_value = make_completion('```json\n{"a": 1}\n```')

        assert await judge_client.complete_json("s", "u") == {"a": 1}

    @pytest.mark.asyncio
    async def test_strips_plain_code_fence(self, judge_client):
        create_mock(judge_client).return_value = make_completion('```\n{"a": 1}\n```')

        assert await judge_client.complete_json("s", "u") == {"a": 1}

    @pytest.mark.asyncio
    async def test_tolerates_surrounding_whitespace(self, judge_client):
        create_mock(judge_client).return_value = make_completion('  \n {"a": 1} \n ')

        assert await judge_client.complete_json("s", "u") == {"a": 1}

    @pytest.mark.asyncio
    async def test_truncated_response_raises_parse_error(self, judge_client):
        create_mock(judge_client).return_value = make_completion('{"a":', finish_reason="length")

        with pytest.raises(JudgeParseError, match="max_tokens"):
            await judge_client.complete_json("s", "u")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("content", [None, ""])
    async def test_empty_response_raises_parse_error(self, judge_client, content):
        create_mock(judge_client).return_value = make_completion(content)

        with pytest.raises(JudgeParseError, match="Empty"):
            await judge_client.complete_json("s", "u")

    @pytest.mark.asyncio
    async def test_invalid_json_raises_parse_error(self, judge_client):
        create_mock(judge_client).return_value = make_completion("not json at all")

        with pytest.raises(JudgeParseError, match="Invalid JSON"):
            await judge_client.complete_json("s", "u")


class TestClientErrors:

    @pytest.mark.asyncio
    async def test_connection_error_wrapped(self, judge_client):
        create_mock(judge_client).side_effect = APIConnectionError(request=REQUEST)

        with pytest.raises(JudgeClientError):
            await judge_client.complete_json("s", "u")

    @pytest.mark.asyncio
    async def test_timeout_wrapped(self, judge_client):
        create_mock(judge_client).side_effect = APITimeoutError(request=REQUEST)

        with pytest.raises(JudgeClientError):
            await judge_client.complete_json("s", "u")

    @pytest.mark.asyncio
    async def test_status_error_wrapped(self, judge_client):
        response = httpx.Response(500, request=REQUEST)
        create_mock(judge_client).side_effect = APIStatusError("server error", response=response, body=None)

        with pytest.raises(JudgeClientError):
            await judge_client.complete_json("s", "u")