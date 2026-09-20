import hashlib
from unittest.mock import mock_open, patch

import pytest

from src.knowledge.ingestion.loaders.text_loader import TextLoader
from src.knowledge.ingestion.loaders.registry import LoaderRegistry
from src.knowledge.documents_schema.raw_document import RawDocument


class TestTextLoaderRegistration:

    def test_registered_under_text_plain(self):
        assert LoaderRegistry.get("text/plain") is TextLoader


class TestTextLoaderLoadDocument:

    def test_raises_when_file_does_not_exist(self):
        loader = TextLoader()

        with patch("src.knowledge.ingestion.loaders.text_loader.os.path.isfile", return_value=False):
            with pytest.raises(FileNotFoundError):
                loader.load_document("missing.txt")

    def test_raises_when_extension_is_not_txt(self):
        loader = TextLoader()

        with patch("src.knowledge.ingestion.loaders.text_loader.os.path.isfile", return_value=True):
            with pytest.raises(ValueError):
                loader.load_document("document.pdf")

    def test_returns_raw_document_with_expected_fields(self):
        loader = TextLoader()
        content = b"plain text content"

        with patch("src.knowledge.ingestion.loaders.text_loader.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=content)):
            result = loader.load_document("/tmp/notes.txt")

        assert isinstance(result, RawDocument)
        assert result.source == "/tmp/notes.txt"
        assert result.content == content
        assert result.content_type == "text/plain"
        assert result.content_hash == hashlib.sha256(content).hexdigest()

    def test_extension_check_is_case_insensitive(self):
        loader = TextLoader()
        content = b"data"

        with patch("src.knowledge.ingestion.loaders.text_loader.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=content)):
            result = loader.load_document("/tmp/NOTES.TXT")

        assert result.content_type == "text/plain"

    def test_opens_file_in_binary_mode(self):
        loader = TextLoader()

        with patch("src.knowledge.ingestion.loaders.text_loader.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=b"data")) as mocked_open:
            loader.load_document("/tmp/notes.txt")

        mocked_open.assert_called_once_with("/tmp/notes.txt", "rb")