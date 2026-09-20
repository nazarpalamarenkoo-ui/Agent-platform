import pytest

from src.knowledge.ingestion.loaders.registry import LoaderRegistry
from src.knowledge.ingestion.loaders.base_loader import BaseLoader


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    """Give each test a private registry dict so registrations made in one
    test (or by the real pdf_loader/text_loader modules imported elsewhere
    in the suite) don't leak in or cause duplicate-registration errors.
    """
    monkeypatch.setattr(LoaderRegistry, "_registry", {})
    yield


class DummyLoader(BaseLoader):
    def load_document(self, source):
        return f"loaded:{source}"


class TestRegister:

    def test_register_adds_loader_to_registry(self):
        LoaderRegistry.register("text/dummy")(DummyLoader)

        assert LoaderRegistry.available() == ["text/dummy"]
        assert LoaderRegistry.get("text/dummy") is DummyLoader

    def test_register_returns_the_class_unchanged(self):
        decorated = LoaderRegistry.register("text/dummy")(DummyLoader)
        assert decorated is DummyLoader

    def test_register_can_be_used_as_decorator(self):
        @LoaderRegistry.register("application/dummy")
        class AnotherLoader(BaseLoader):
            def load_document(self, source):
                return source

        assert LoaderRegistry.get("application/dummy") is AnotherLoader

    def test_duplicate_registration_raises_value_error(self):
        LoaderRegistry.register("text/dummy")(DummyLoader)

        with pytest.raises(ValueError):
            LoaderRegistry.register("text/dummy")(DummyLoader)


class TestGet:

    def test_get_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError):
            LoaderRegistry.get("nonexistent/type")

    def test_get_error_message_lists_available_loaders(self):
        LoaderRegistry.register("text/dummy")(DummyLoader)

        with pytest.raises(ValueError, match="text/dummy"):
            LoaderRegistry.get("nonexistent/type")


class TestCreate:

    def test_create_instantiates_registered_loader(self):
        LoaderRegistry.register("text/dummy")(DummyLoader)

        instance = LoaderRegistry.create("text/dummy")

        assert isinstance(instance, DummyLoader)
        assert instance.load_document("src.txt") == "loaded:src.txt"

    def test_create_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError):
            LoaderRegistry.create("nonexistent/type")


class TestAvailable:

    def test_available_is_empty_when_no_loaders_registered(self):
        assert LoaderRegistry.available() == []

    def test_available_lists_all_registered_names(self):
        LoaderRegistry.register("text/dummy")(DummyLoader)
        LoaderRegistry.register("application/dummy")(DummyLoader)

        assert set(LoaderRegistry.available()) == {"text/dummy", "application/dummy"}