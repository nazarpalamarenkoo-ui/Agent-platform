import pytest

from src.knowledge.acquisition.discovery.query_builder import (
    DEFAULT_MODIFIERS,
    QueryBuilder,
)


class TestQueryBuilderInit:

    def test_rejects_min_strategies_below_one(self):
        with pytest.raises(ValueError):
            QueryBuilder(min_strategies=0)

    def test_rejects_max_below_min(self):
        with pytest.raises(ValueError):
            QueryBuilder(min_strategies=4, max_strategies=3)

    def test_uses_default_modifiers(self):
        assert QueryBuilder().modifiers == DEFAULT_MODIFIERS

    def test_copies_custom_modifiers_list(self):
        custom = ["a", "b"]
        builder = QueryBuilder(modifiers=custom)
        custom.append("c")
        assert builder.modifiers == ["a", "b"]


class TestQueryBuilderBuild:

    def test_short_query_gets_all_modifiers(self):
        strategies = QueryBuilder().build("kafka")

        assert strategies == [f"kafka {m}" for m in DEFAULT_MODIFIERS]

    def test_long_query_is_limited_to_min_strategies(self):
        query = "how to design a scalable event driven backend"  # > 6 words

        strategies = QueryBuilder().build(query)

        assert len(strategies) == 3
        assert strategies == [f"{query} {m}" for m in DEFAULT_MODIFIERS[:3]]

    def test_six_words_is_still_short_query(self):
        strategies = QueryBuilder().build("one two three four five six")

        assert len(strategies) == 5

    def test_skips_modifiers_already_in_query_case_insensitive(self):
        strategies = QueryBuilder().build("Kafka PDF")

        assert "Kafka PDF pdf" not in strategies
        assert len(strategies) == len(DEFAULT_MODIFIERS) - 1

    def test_normalizes_whitespace(self):
        strategies = QueryBuilder(modifiers=["pdf"], min_strategies=1).build("  kafka    streams \n")

        assert strategies == ["kafka streams pdf"]

    def test_returns_empty_when_all_modifiers_present(self):
        builder = QueryBuilder(modifiers=["pdf", "spec"], min_strategies=1)

        assert builder.build("pdf spec") == []

    def test_fewer_modifiers_than_min_returns_what_is_available(self):
        builder = QueryBuilder(modifiers=["pdf"], min_strategies=3, max_strategies=6)

        assert builder.build("kafka") == ["kafka pdf"]

    def test_respects_max_strategies(self):
        builder = QueryBuilder(modifiers=list("abcdef"), min_strategies=1, max_strategies=2)

        assert len(builder.build("x")) == 2

    @pytest.mark.parametrize("query", ["", "   ", "\n\t"])
    def test_empty_query_raises(self, query):
        with pytest.raises(ValueError):
            QueryBuilder().build(query)