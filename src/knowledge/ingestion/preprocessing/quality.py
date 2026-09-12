import re
from typing import Literal
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk
from src.knowledge.ingestion.normalization.normalizer import Normalizer

QualityDecision = Literal["index", "low_priority", "reject"]

class QualityScorer:
    def __init__(
        self,
        normalizer: Normalizer,
        symbol_patterns: tuple[str, ...] | None = None,
        word_patterns: set[str] | None = None,
        min_length: int = 200,
        max_length: int = 500,
    ):
        self.normalizer = normalizer
        self.min_length = min_length
        self.max_length = max_length

        self.word_patterns = word_patterns or {
            "function", "class", "algorithm", "method",
            "variable", "return", "import",
        }

        self.symbol_patterns = symbol_patterns or (
            "->", "==", "!=", "++", "--",
            "{", "}", "[", "]", "(", ")",
        )

        # Base weights — apply to ANY text, code or prose alike.
        self.base_weights = {
            "length": 0.30,
            "diversity": 0.30,
            "boilerplate": 0.40,
        }

        # Bonus weights — additive on top of base_score, reward technical/code content instead of penalizing its absence.
        self.bonus_weights = {
            "technical": 0.15,
            "code": 0.10,
        }

    def _score_length(self, token_count: int) -> float:

        if token_count <= 0:
            return 0.0

        if self.min_length <= token_count <= self.max_length:
            return 1.0

        if token_count < self.min_length:
            return token_count / self.min_length

        overflow_limit = self.max_length * 2
        if token_count >= overflow_limit:
            return 0.0

        return 1.0 - (token_count - self.max_length) / (overflow_limit - self.max_length)

    def _score_diversity(self, words: list[str]) -> float:
        if not words:
            return 0.0

        return len(set(words)) / len(words)

    def _score_technical_density(self, chunk_text: str) -> float:

        words = re.findall(r"\b\w+\b", chunk_text.lower())

        total_words = len(words)

        if total_words == 0:
            return 0.0

        match_words = sum(1 for word in words if word in self.word_patterns)
        match_symbols = sum(chunk_text.count(pattern) for pattern in self.symbol_patterns)

        words_score = min(1.0, (match_words / total_words) * 5)
        symbols_score = min(1.0, (match_symbols / total_words) * 15)

        return (words_score + symbols_score) / 2

    def _score_boilerplate(self, chunk_text: str, boilerplate_lines: set[str]) -> float:
        original_len = len(chunk_text)

        if original_len == 0:
            return 0.0

        cleaned_text = self.normalizer._remove_boilerplate(chunk_text, boilerplate_lines)
        cleaned_len = len(cleaned_text)

        removed_ratio = (original_len - cleaned_len) / original_len

        return 1.0 - removed_ratio

    def _score_code_examples(self, chunk_text: str) -> float:

        lines = chunk_text.splitlines()
        total_lines = max(len(lines), 1)

        # 1. Fenced code blocks
        fenced_blocks = len(re.findall(r"```[\w+-]*\n[\s\S]*?\n```", chunk_text))

        # 2. Inline code (`docker compose`, `uvicorn`, ...)
        inline_code = len(re.findall(r"`[^`\n]+`", chunk_text))

        # 3. Code-like lines
        code_like_lines = sum(
            1 for line in lines
            if re.match(
                r"^\s*(def |class |async |import |from |const |let |function |return |if |for |while |docker |git |pip |npm )",
                line
            )
        )

        fenced_score = min(1.0, fenced_blocks * 0.6)
        inline_score = min(1.0, (inline_code / total_lines) * 8)
        pattern_score = min(1.0, (code_like_lines / total_lines) * 10)

        return (fenced_score + inline_score + pattern_score) / 3

    def score(self, chunk: KnowledgeChunk, boilerplate_lines: set[str]) -> float:
        text = chunk.text

        words = re.findall(r"\b\w+\b", text.lower())

        length = self._score_length(chunk.token_count)
        diversity = self._score_diversity(words)
        boilerplate = self._score_boilerplate(text, boilerplate_lines)
        technical = self._score_technical_density(text)
        code = self._score_code_examples(text)

        # Base score: applies equally to prose and code, must stand on its own as a valid 0.0-1.0 estimate for plain text with zero
        base_score = (
            length * self.base_weights["length"] +
            diversity * self.base_weights["diversity"] +
            boilerplate * self.base_weights["boilerplate"]
        )

        # Bonus: rewards technical/code content on top of base_score,
        bonus = (
            technical * self.bonus_weights["technical"] +
            code * self.bonus_weights["code"]
        )

        final_score = base_score + bonus

        return round(min(max(final_score, 0.0), 1.0), 3)

    @staticmethod
    def gate(score: float) -> QualityDecision:

        if score >= 0.80:
            return "index"

        if score >= 0.60:
            return "low_priority"

        return "reject"