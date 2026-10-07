import pytest
from pydantic import ValidationError

from src.knowledge.acquisition.judge.models import (
    DocumentDecision,
    JudgeItem,
    JudgeResponse,
    TrustBreakdown,
)
from src.knowledge.acquisition.judge.prompts import (
    DOCUMENT_BLOCK_TEMPLATE,
    DOCUMENT_CATEGORIES,
    JUDGE_SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)


class TestTrustBreakdown:

    @pytest.mark.parametrize("value", [0.0, 0.5, 1.0])
    def test_accepts_values_in_range(self, value):
        trust = TrustBreakdown(educational=value, implementation=value, authority=value)
        assert trust.educational == value

    @pytest.mark.parametrize("value", [-0.01, 1.01])
    @pytest.mark.parametrize("field", ["educational", "implementation", "authority"])
    def test_rejects_values_out_of_range(self, field, value):
        data = {"educational": 0.5, "implementation": 0.5, "authority": 0.5, field: value}

        with pytest.raises(ValidationError):
            TrustBreakdown(**data)


class TestJudgeResponse:

    def test_parses_valid_payload(self):
        payload = {
            "results": [
                {
                    "key": "k",
                    "reason": "r",
                    "document_category": "paper",
                    "trust": {"educational": 0.1, "implementation": 0.2, "authority": 0.3},
                }
            ]
        }

        response = JudgeResponse.model_validate(payload)

        assert isinstance(response.results[0], JudgeItem)
        assert response.results[0].trust.authority == 0.3

    def test_missing_results_is_invalid(self):
        with pytest.raises(ValidationError):
            JudgeResponse.model_validate({})


class TestDocumentDecision:

    def test_values(self):
        assert DocumentDecision.ACCEPT.value == "accept"
        assert DocumentDecision.REJECT.value == "reject"
        assert DocumentDecision("accept") is DocumentDecision.ACCEPT


class TestPrompts:

    def test_system_prompt_lists_all_categories(self):
        for category in DOCUMENT_CATEGORIES:
            assert f'"{category}"' in JUDGE_SYSTEM_PROMPT

    def test_system_prompt_contains_output_schema(self):
        assert '"results"' in JUDGE_SYSTEM_PROMPT
        assert '"document_category"' in JUDGE_SYSTEM_PROMPT

    def test_judge_error_is_not_an_allowed_category(self):
        assert "judge_error" not in DOCUMENT_CATEGORIES

    def test_document_block_template_renders(self):
        block = DOCUMENT_BLOCK_TEMPLATE.format(
            key="k1", title="T", domain="d.com", snippet="S", headings="H", first_page="F"
        )

        assert block.startswith('<document key="k1">')
        assert block.endswith("</document>")
        assert "Title: T" in block
        assert "Text start: F" in block

    def test_user_prompt_template_renders(self):
        prompt = USER_PROMPT_TEMPLATE.format(count=2, keys='"a", "b"', documents="DOCS")

        assert "following 2 documents" in prompt
        assert '"a", "b"' in prompt
        assert prompt.endswith("DOCS")