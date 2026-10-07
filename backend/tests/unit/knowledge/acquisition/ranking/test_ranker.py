import pytest

from src.knowledge.acquisition.ranking.ranker import DOMAIN_SCORES, FORMAT_SCORES, Ranker
from src.knowledge.documents_schema.discovery_model import DiscoveryResult


def make_result(
    title="title",
    url="https://example.com/a",
    domain="example.com",
    snippet="snippet",
    mime_type="text/html",
):
    return DiscoveryResult(title=title, url=url, domain=domain, snippet=snippet, mime_type=mime_type)


@pytest.fixture
def ranker():
    return Ranker()


class TestComponentScores:

    def test_known_domain_score(self, ranker):
        assert ranker._domain_score(make_result(domain="arxiv.org")) == DOMAIN_SCORES["arxiv.org"]

    def test_unknown_domain_uses_default(self, ranker):
        assert ranker._domain_score(make_result(domain="unknown.xyz")) == 0.1

    def test_known_format_score(self, ranker):
        assert ranker._format_score(make_result(mime_type="application/pdf")) == FORMAT_SCORES["application/pdf"]

    def test_unknown_format_uses_default(self, ranker):
        assert ranker._format_score(make_result(mime_type="image/png")) == 0.1

    def test_custom_defaults(self):
        custom = Ranker(domain_scores={}, format_scores={}, default_domain_score=0.5, default_format_score=0.2)

        result = make_result()
        assert custom._domain_score(result) == 0.5
        assert custom._format_score(result) == 0.2


class TestTextSimilarity:

    def test_tokenize_lowercases_and_splits_words(self, ranker):
        assert ranker._tokenize("Hello, World! hello") == {"hello", "world"}

    def test_title_similarity_full_overlap(self, ranker):
        result = make_result(title="Python Async Guide")

        assert ranker._title_similarity("python async", result) == 1.0

    def test_title_similarity_partial_overlap(self, ranker):
        result = make_result(title="Python basics")

        assert ranker._title_similarity("python async", result) == 0.5

    def test_title_similarity_no_overlap(self, ranker):
        assert ranker._title_similarity("kafka", make_result(title="cooking")) == 0.0

    def test_title_similarity_empty_query_tokens(self, ranker):
        assert ranker._title_similarity("!!!", make_result()) == 0.0

    def test_keyword_overlap_uses_snippet(self, ranker):
        result = make_result(snippet="kafka streams tutorial")

        assert ranker._keyword_overlap("kafka streams", result) == 1.0

    def test_keyword_overlap_empty_query_tokens(self, ranker):
        assert ranker._keyword_overlap("???", make_result()) == 0.0


class TestCalculateScore:

    def test_sums_all_components(self, ranker):
        result = make_result(
            title="python", snippet="python", domain="arxiv.org", mime_type="application/pdf"
        )

        score = ranker._calculate_score("python", result)

        assert score == pytest.approx(0.35 + 0.40 + 1.0 + 1.0)


class TestRank:

    def test_empty_query_returns_empty_list(self, ranker):
        assert ranker.rank("", [make_result()]) == []

    def test_empty_results_returns_empty_list(self, ranker):
        assert ranker.rank("query", []) == []

    def test_sorts_by_score_descending(self, ranker):
        weak = make_result(title="x", snippet="x", domain="medium.com", mime_type="text/plain")
        strong = make_result(title="x", snippet="x", domain="arxiv.org", mime_type="application/pdf")
        middle = make_result(title="x", snippet="x", domain="github.com", mime_type="text/html")

        ranked = ranker.rank("query", [weak, strong, middle])

        assert ranked == [strong, middle, weak]

    def test_title_match_can_outweigh_domain(self, ranker):
        relevant = make_result(title="kafka streams", snippet="kafka streams", domain="medium.com")
        irrelevant = make_result(title="other", snippet="other", domain="arxiv.org")

        ranked = ranker.rank("kafka streams", [irrelevant, relevant])

        assert ranked[0] is relevant

    def test_limits_to_top_n(self):
        ranker = Ranker(top_n=2)
        results = [make_result(url=f"https://e.com/{i}") for i in range(5)]

        assert len(ranker.rank("q", results)) == 2

    def test_does_not_mutate_input(self, ranker):
        weak = make_result(domain="medium.com")
        strong = make_result(domain="arxiv.org")
        original = [weak, strong]

        ranker.rank("q", original)

        assert original == [weak, strong]