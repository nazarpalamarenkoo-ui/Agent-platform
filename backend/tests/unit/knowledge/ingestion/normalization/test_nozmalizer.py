import pytest

from src.knowledge.ingestion.normalization.normalizer import Normalizer
from src.knowledge.documents_schema.knowledge_chunck import KnowledgeChunk


def make_chunk(text, index=0):
    return KnowledgeChunk(chunk_index=index, text=text, token_count=len(text.split()))


class TestNormalize:

    def test_short_chunks_are_dropped(self):
        normalizer = Normalizer(min_lenght=50)
        chunks = [make_chunk("too short", 0), make_chunk("also short", 1)]

        result = normalizer.normalize(chunks)

        assert result == []

    def test_long_enough_distinct_chunks_are_kept(self):
        normalizer = Normalizer(min_lenght=10)
        chunks = [
            make_chunk("this chunk talks about databases and indexing", 0),
            make_chunk("this other chunk talks about caching strategies", 1),
        ]

        result = normalizer.normalize(chunks)

        assert len(result) == 2
        texts = {c.text for c in result}
        assert "this chunk talks about databases and indexing" in texts
        assert "this other chunk talks about caching strategies" in texts

    def test_single_chunk_whose_full_text_is_classified_as_boilerplate_is_dropped(self):
        normalizer = Normalizer(min_lenght=10)
        chunks = [make_chunk("this text is definitely long enough to survive", 0)]

        result = normalizer.normalize(chunks)

        assert result == []

    def test_whitespace_is_collapsed_and_stripped(self):
        normalizer = Normalizer(min_lenght=5)
        chunks = [
            make_chunk("  lots\n\nof   whitespace   here  ", 0),
            make_chunk("a completely different second chunk", 1),
        ]

        result = normalizer.normalize(chunks)

        first = next(c for c in result if "whitespace" in c.text)
        assert first.text == "lots of whitespace here"

    def test_unicode_is_nfkc_normalized(self):
        normalizer = Normalizer(min_lenght=1)
        # "ﬁ" (U+FB01, ligature) should normalize to "fi"
        chunks = [
            make_chunk("scientiﬁc text long enough", 0),
            make_chunk("a different unrelated chunk here", 1),
        ]

        result = normalizer.normalize(chunks)

        target = next(c for c in result if "scienti" in c.text)
        assert "ﬁ" not in target.text
        assert "fi" in target.text

    def test_original_chunks_are_not_mutated(self):
        normalizer = Normalizer(min_lenght=1)
        original = make_chunk("  extra   spaces  ", 0)
        other = make_chunk("a totally different chunk", 1)

        normalizer.normalize([original, other])

        assert original.text == "  extra   spaces  "

    def test_boilerplate_detection_runs_against_original_multiline_text(self):
        normalizer = Normalizer(min_lenght=1, boilerplate_threshold=0.6)
        header = "Copyright 2024 Example Corp"
        chunks = [
            make_chunk(f"{header}\nunique content one here", 0),
            make_chunk(f"{header}\nunique content two here", 1),
            make_chunk(f"{header}\nunique content three here", 2),
        ]

        # NOTE: the real Normalizer exposes this as a *public* method
        # (`find_boilerplate`), not `_find_boilerplate`.
        boilerplate = normalizer.find_boilerplate(chunks)

        assert header in boilerplate

    def test_boilerplate_survives_in_final_text_because_whitespace_collapse_runs_first(self):
        normalizer = Normalizer(min_lenght=1, boilerplate_threshold=0.6)
        header = "Copyright 2024 Example Corp"
        chunks = [
            make_chunk(f"{header}\nunique content one here", 0),
            make_chunk(f"{header}\nunique content two here", 1),
            make_chunk(f"{header}\nunique content three here", 2),
        ]

        result = normalizer.normalize(chunks)

        for chunk in result:
            assert "Copyright 2024 Example Corp" in chunk.text
            assert "unique content" in chunk.text

    def test_boilerplate_not_removed_when_below_threshold(self):
        normalizer = Normalizer(min_lenght=1, boilerplate_threshold=0.9)
        header = "Shared header line"
        chunks = [
            make_chunk(f"{header}\ncontent one here please", 0),
            make_chunk("no shared header at all in this one", 1),
        ]

        result = normalizer.normalize(chunks)

        joined = " ".join(c.text for c in result)
        assert "Shared header line" in joined

    def test_empty_chunk_list_returns_empty_list(self):
        normalizer = Normalizer()
        assert normalizer.normalize([]) == []

    def test_preserves_chunk_index_and_document_id(self):
        normalizer = Normalizer(min_lenght=1)
        chunk = KnowledgeChunk(document_id=7, chunk_index=3, text="keep me around please", token_count=4)
        other = KnowledgeChunk(document_id=7, chunk_index=4, text="a different unrelated chunk", token_count=4)

        result = normalizer.normalize([chunk, other])

        target = next(c for c in result if c.chunk_index == 3)
        assert target.document_id == 7
        assert target.chunk_index == 3

    def test_default_thresholds(self):
        normalizer = Normalizer()
        assert normalizer.min_lenght == 50
        assert normalizer.boilerplate_threshold == 0.7