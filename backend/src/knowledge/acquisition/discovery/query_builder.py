from typing import Optional


DEFAULT_MODIFIERS = [
    "pdf",
    "whitepaper",
    "architecture",
    "specification",
    "research paper",
]


LONG_QUERY_WORD_THRESHOLD = 6


class QueryBuilder:

    def __init__(
        self,
        modifiers: Optional[list[str]] = None,
        min_strategies: int = 3,
        max_strategies: int = 6,
    ):
        if min_strategies < 1:
            raise ValueError("min_strategies must be >= 1")
        if max_strategies < min_strategies:
            raise ValueError("max_strategies must be >= min_strategies")

        self.modifiers = list(modifiers) if modifiers is not None else list(DEFAULT_MODIFIERS)
        self.min_strategies = min_strategies
        self.max_strategies = max_strategies

    def build(self, query: str) -> list[str]:
        normalized = self._normalize(query)

        available_modifiers = self._filter_already_present(normalized)

        target_count = self._resolve_target_count(normalized, available_modifiers)

        selected = available_modifiers[:target_count]

        return [self._build_strategy(normalized, modifier) for modifier in selected]

    def _normalize(self, query: str) -> str:
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        return " ".join(query.strip().split())

    def _is_long_query(self, normalized_query: str) -> bool:
        word_count = len(normalized_query.split())
        return word_count > LONG_QUERY_WORD_THRESHOLD

    def _modifier_already_present(self, normalized_query: str, modifier: str) -> bool:
        return modifier.lower() in normalized_query.lower()

    def _filter_already_present(self, normalized_query: str) -> list[str]:
        return [
            modifier
            for modifier in self.modifiers
            if not self._modifier_already_present(normalized_query, modifier)
        ]

    def _resolve_target_count(
        self,
        normalized_query: str,
        available_modifiers: list[str],
    ) -> int:
        if self._is_long_query(normalized_query):
            desired = self.min_strategies
        else:
            desired = self.max_strategies

        return max(
            self.min_strategies,
            min(desired, self.max_strategies, len(available_modifiers)),
        ) if available_modifiers else 0

    def _build_strategy(self, normalized_query: str, modifier: str) -> str:
        return f"{normalized_query} {modifier}"