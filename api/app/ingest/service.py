"""Ingestion: HTML -> sections -> store. The same path for fixtures and for EDGAR."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.fixtures.corpus import fixture_filings
from app.ingest.edgar import EdgarClient
from app.ingest.parser import parse_filing_html
from app.models import Filing, Section
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


class Ingestor:
    def __init__(self, store: Store) -> None:
        self._store = store

    def ingest_html(self, filing: Filing, html: str) -> IngestResult:
        sections = [s for s in parse_filing_html(html, filing.id) if s.item in KEPT_ITEMS]
        if len(sections) < MIN_SECTIONS:
            raise IngestError(
                f"{filing.id}: found {len(sections)} Item sections; the document does not look "
                "like a 10-K"
            )
        self.store(filing, sections)
        log.info("ingested %s (%d sections)", filing.id, len(sections))
        return IngestResult(filing, len(sections))

    def store(self, filing: Filing, sections: list[Section]) -> None:
        """Persist a parsed filing. Later milestones extend this (chunks, graph)."""
        self._store.add_filing(filing, sections)

    def ingest_fixtures(self) -> list[IngestResult]:
        return [self.ingest_html(f, html) for f, html in fixture_filings()]

    def ingest_edgar(self, client: EdgarClient, ticker: str, limit: int = 3) -> list[IngestResult]:
        results = []
        for found in client.annual_reports(ticker, limit=limit):
            results.append(self.ingest_html(found.filing, client.document(found.document_url)))
        return results
