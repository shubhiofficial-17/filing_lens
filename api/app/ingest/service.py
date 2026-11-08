"""Ingestion: HTML -> sections -> chunks -> embeddings -> store.

The same path serves the fixture corpus and EDGAR."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.fixtures.corpus import fixture_filings
from app.ingest.edgar import EdgarClient
from app.ingest.parser import parse_filing_html
from app.models import Filing, Section
from app.rag.chunking import chunk_section, index_text
from app.rag.embeddings import Embedder, HashingEmbedder
from app.store.base import Store

log = logging.getLogger(__name__)

# Items worth keeping. Exhibits, signatures and the cover page add noise to retrieval.
KEPT_ITEMS = {"1", "1A", "1C", "2", "3", "5", "7", "7A", "8", "9A"}
MIN_SECTIONS = 2


class IngestError(Exception):
    pass


@dataclass
class IngestResult:
    filing: Filing
    sections: int
    chunks: int = 0


class Ingestor:
    def __init__(self, store: Store, embedder: Embedder | None = None) -> None:
        self._store = store
        self._embedder = embedder or HashingEmbedder()

    def ingest_html(self, filing: Filing, html: str) -> IngestResult:
        sections = [s for s in parse_filing_html(html, filing.id) if s.item in KEPT_ITEMS]
        if len(sections) < MIN_SECTIONS:
            raise IngestError(
                f"{filing.id}: found {len(sections)} Item sections; the document does not look "
                "like a 10-K"
            )
        chunks = self.store(filing, sections)
        log.info("ingested %s (%d sections, %d chunks)", filing.id, len(sections), chunks)
        return IngestResult(filing, len(sections), chunks)

    def store(self, filing: Filing, sections: list[Section]) -> int:
        self._store.add_filing(filing, sections)
        chunks, texts = [], []
        for section in sections:
            for chunk in chunk_section(section, filing):
                chunks.append(chunk)
                texts.append(index_text(chunk, filing.company, section.title))
        if chunks:
            self._store.add_chunks(chunks, texts, self._embedder.embed(texts))
        return len(chunks)

    def ingest_fixtures(self) -> list[IngestResult]:
        return [self.ingest_html(f, html) for f, html in fixture_filings()]

    def ingest_edgar(self, client: EdgarClient, ticker: str, limit: int = 3) -> list[IngestResult]:
        results = []
        for found in client.annual_reports(ticker, limit=limit):
            results.append(self.ingest_html(found.filing, client.document(found.document_url)))
        return results
