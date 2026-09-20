import pytest

from src.knowledge.ingestion.loaders.base_loader import BaseLoader


class TestBaseLoader:

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseLoader()

    def test_subclass_must_implement_load_document(self):
        class IncompleteLoader(BaseLoader):
            pass

        with pytest.raises(TypeError):
            IncompleteLoader()

    def test_subclass_implementing_load_document_can_be_instantiated(self):
        class ConcreteLoader(BaseLoader):
            def load_document(self, source):
                return source

        loader = ConcreteLoader()
        assert loader.load_document("x") == "x"