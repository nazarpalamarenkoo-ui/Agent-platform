import asyncio
import logging
import re

import fitz
from bs4 import BeautifulSoup
from typing import cast
from src.knowledge.acquisition.dedup.url_normalizer import calculate_hash
from src.knowledge.acquisition.fetch import Fetcher
from src.knowledge.documents_schema.discovery_model import DiscoveryResult
from src.knowledge.documents_schema.document_candidate import DocumentCandidate
from src.knowledge.documents_schema.raw_document import RawDocument

logger = logging.getLogger(__name__)

HTML_MIME_TYPES = {"text/html"}
PDF_MIME_TYPES = {"application/pdf"}


class PreviewFetcher:

    def __init__(
        self,
        fetcher: Fetcher,
        preview_chars: int = 1500,
        max_headings: int = 10,
    ):
        self.fetcher = fetcher
        self.preview_chars = preview_chars
        self.max_headings = max_headings

    async def fetch_many(
        self,
        candidates: list[DiscoveryResult],
        query: str,
    ) -> list[DocumentCandidate]:
        if not candidates:
            return []

        results = await asyncio.gather(
            *[self._fetch_one(candidate, query) for candidate in candidates],
            return_exceptions=True,
        )

        previews: list[DocumentCandidate] = []
        for candidate, result in zip(candidates, results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Preview fetch failed for %s: %s", candidate.url, result
                )
                continue
            previews.append(result)
        
        return previews

    async def _fetch_one(
        self,
        candidate: DiscoveryResult,
        query: str,
    ) -> DocumentCandidate:
        raw_doc = await self.fetcher.fetch(candidate.url)

        headings, first_page = self._parse_preview(raw_doc)

        return DocumentCandidate(
            key=calculate_hash(candidate),
            query=query,
            title=candidate.title,
            url=candidate.url,
            domain=candidate.domain,
            snippet=candidate.snippet,
            headings=headings,
            first_page=first_page,
        )

    def _parse_preview(self, raw_doc: RawDocument) -> tuple[list[str], str]:
        if raw_doc.content_type in PDF_MIME_TYPES:
            return self._parse_pdf_preview(raw_doc)

        if raw_doc.content_type in HTML_MIME_TYPES:
            return self._parse_html_preview(raw_doc)

        return self._parse_plain_text_preview(raw_doc)

    def _parse_html_preview(self, raw_doc: RawDocument) -> tuple[list[str], str]:
        soup = BeautifulSoup(raw_doc.content, "html.parser")

        headings = [
            tag.get_text(strip=True)
            for tag in soup.find_all(["h1", "h2", "h3"])
            if tag.get_text(strip=True)
        ][: self.max_headings]

        text = soup.get_text(separator=" ", strip=True)
        first_page = text[: self.preview_chars]

        return headings, first_page

    def _parse_pdf_preview(self, raw_doc: RawDocument) -> tuple[list[str], str]:
        with fitz.open(stream=raw_doc.content, filetype="pdf") as pdf:
            if pdf.page_count == 0:
                return [], ""

            first_page: str = cast(str, pdf[0].get_text("text"))
            headings = self._extract_pdf_headings(pdf)

        return headings, first_page[: self.preview_chars]

    def _extract_pdf_headings(self, pdf: "fitz.Document") -> list[str]:
        toc = pdf.get_toc()
        return [str(title) for _level, title, _page in toc][: self.max_headings]

    def _parse_plain_text_preview(self, raw_doc: RawDocument) -> tuple[list[str], str]:
        text = raw_doc.content.decode("utf-8", errors="ignore")
        cleaned = re.sub(r"\s+", " ", text).strip()
        return [], cleaned[: self.preview_chars]