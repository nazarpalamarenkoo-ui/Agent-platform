import pytest

from src.knowledge.ingestion.extraction.registry import ExtractorRegistry
from src.knowledge.ingestion.extraction.base_extractor import BaseExtractor


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    """Give each test a private registry dict so registrations made in one
    test (or by the real html_extractor/pdf_extractor/text_extractor modules
    imported elsewhere in the suite) don't leak in or cause duplicate-
    registration errors.
    """
    monkeypatch.setattr(ExtractorRegistry, "_registry", {})
    yield


class DummyExtractor(BaseExtractor):
    def extract(self, document):
        return f"extracted:{document}"


class TestRegister:

    def test_register_adds_extractor_to_registry(self):
        ExtractorRegistry.register("text/dummy")(DummyExtractor)

        assert ExtractorRegistry.available() == ["text/dummy"]
        assert ExtractorRegistry.get("text/dummy") is DummyExtractor

    def test_register_returns_the_class_unchanged(self):
        decorated = ExtractorRegistry.register("text/dummy")(DummyExtractor)
        assert decorated is DummyExtractor

    def test_register_can_be_used_as_decorator(self):
        @ExtractorRegistry.register("application/dummy")
        class AnotherExtractor(BaseExtractor):
            def extract(self, document):
                return document

        assert ExtractorRegistry.get("application/dummy") is AnotherExtractor

    def test_duplicate_registration_raises_value_error(self):
        ExtractorRegistry.register("text/dummy")(DummyExtractor)

        with pytest.raises(ValueError):
            ExtractorRegistry.register("text/dummy")(DummyExtractor)


class TestGet:

    def test_get_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError):
            ExtractorRegistry.get("nonexistent/type")

    def test_get_error_message_lists_available_extractors(self):
        ExtractorRegistry.register("text/dummy")(DummyExtractor)

        with pytest.raises(ValueError, match="text/dummy"):
            ExtractorRegistry.get("nonexistent/type")


class TestCreate:

    def test_create_instantiates_registered_extractor(self):
        ExtractorRegistry.register("text/dummy")(DummyExtractor)

        instance = ExtractorRegistry.create("text/dummy")

        assert isinstance(instance, DummyExtractor)
        assert instance.extract("doc") == "extracted:doc"

    def test_create_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError):
            ExtractorRegistry.create("nonexistent/type")


class TestAvailable:

    def test_available_is_empty_when_no_extractors_registered(self):
        assert ExtractorRegistry.available() == []

    def test_available_lists_all_registered_names(self):
        ExtractorRegistry.register("text/dummy")(DummyExtractor)
        ExtractorRegistry.register("application/dummy")(DummyExtractor)

        assert set(ExtractorRegistry.available()) == {"text/dummy", "application/dummy"}