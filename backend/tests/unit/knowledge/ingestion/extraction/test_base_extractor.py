import pytest

from src.knowledge.ingestion.extraction.base_extractor import BaseExtractor, ExtractedDocument


class TestBaseExtractor:

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseExtractor()

    def test_subclass_must_implement_extract(self):
        class IncompleteExtractor(BaseExtractor):
            pass

        with pytest.raises(TypeError):
            IncompleteExtractor()

    def test_subclass_implementing_extract_can_be_instantiated(self):
        class ConcreteExtractor(BaseExtractor):
            def extract(self, document):
                return ExtractedDocument(text="ok", metadata={})

        extractor = ConcreteExtractor()
        result = extractor.extract(document=None)

        assert isinstance(result, ExtractedDocument)
        assert result.text == "ok"


class TestExtractedDocument:

    def test_stores_text_and_metadata(self):
        doc = ExtractedDocument(text="hello", metadata={"source": "x"})

        assert doc.text == "hello"
        assert doc.metadata == {"source": "x"}