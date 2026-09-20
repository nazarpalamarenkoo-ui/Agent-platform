import hashlib
from unittest.mock import mock_open, patch

import pytest

from src.knowledge.ingestion.loaders.pdf_loader import PDFLoader
from src.knowledge.ingestion.loaders.registry import LoaderRegistry
from src.knowledge.documents_schema.raw_document import RawDocument


class TestPDFLoaderRegistration:

    def test_registered_under_application_pdf(self):
        assert LoaderRegistry.get("application/pdf") is PDFLoader


class TestPDFLoaderLoadDocument:

    def test_raises_when_file_does_not_exist(self):
        loader = PDFLoader()

        with patch("src.knowledge.ingestion.loaders.pdf_loader.os.path.isfile", return_value=False):
            with pytest.raises(FileNotFoundError):
                loader.load_document("missing.pdf")

    def test_raises_when_extension_is_not_pdf(self):
        loader = PDFLoader()

        with patch("src.knowledge.ingestion.loaders.pdf_loader.os.path.isfile", return_value=True):
            with pytest.raises(ValueError):
                loader.load_document("document.txt")

    def test_returns_raw_document_with_expected_fields(self):
        loader = PDFLoader()
        content = b"%PDF-1.4 fake pdf bytes"

        with patch("src.knowledge.ingestion.loaders.pdf_loader.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=content)):
            result = loader.load_document("/tmp/report.pdf")

        assert isinstance(result, RawDocument)
        assert result.source == "/tmp/report.pdf"
        assert result.content == content
        assert result.content_type == "application/pdf"
        assert result.content_hash == hashlib.sha256(content).hexdigest()

    def test_extension_check_is_case_insensitive(self):
        loader = PDFLoader()
        content = b"data"

        with patch("src.knowledge.ingestion.loaders.pdf_loader.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=content)):
            result = loader.load_document("/tmp/REPORT.PDF")

        assert result.content_type == "application/pdf"

    def test_opens_file_in_binary_mode(self):
        loader = PDFLoader()

        with patch("src.knowledge.ingestion.loaders.pdf_loader.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=b"data")) as mocked_open:
            loader.load_document("/tmp/report.pdf")

        mocked_open.assert_called_once_with("/tmp/report.pdf", "rb")