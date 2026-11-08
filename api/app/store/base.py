"""The storage contract. Two implementations: InMemoryStore (tests, evaluation, quick runs)
and PostgresStore (pgvector). One contract test suite runs against both."""

from __future__ import annotations

from typing import Protocol

from app.models import Chunk, Filing, Hit, SearchFilter, Section


class Store(Protocol):
    def add_filing(self, filing: Filing, sections: list[Section]) -> None:
        """Insert or replace a filing and its sections."""

    def list_filings(self) -> list[Filing]:
        """All filings, ordered by ticker then fiscal year."""

    def get_filing(self, filing_id: str) -> Filing | None: ...

    def list_sections(self, filing_id: str) -> list[Section]: ...

    def get_section(self, section_id: str) -> Section | None: ...

    def count_filings(self) -> int: ...

    def add_chunks(
        self, chunks: list[Chunk], index_texts: list[str], vectors: list[list[float]]
    ) -> None:
        """Add chunks of filings already stored. Re-adding a filing drops its old chunks."""

    def count_chunks(self) -> int: ...

    def get_chunks(self, ids: list[str]) -> list[Chunk]:
        """Chunks by id, in the order given; unknown ids are skipped."""

    def vector_search(
        self, vector: list[float], k: int, filt: SearchFilter | None = None
    ) -> list[Hit]:
        """Nearest chunks by cosine similarity, best first."""
