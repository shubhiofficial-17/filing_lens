"""The storage contract. Two implementations: InMemoryStore (tests, evaluation, quick runs)
and PostgresStore (pgvector). One contract test suite runs against both."""

from __future__ import annotations

from typing import Protocol

from app.models import Filing, Section


class Store(Protocol):
    def add_filing(self, filing: Filing, sections: list[Section]) -> None:
        """Insert or replace a filing and its sections."""

    def list_filings(self) -> list[Filing]:
        """All filings, ordered by ticker then fiscal year."""

    def get_filing(self, filing_id: str) -> Filing | None: ...

    def list_sections(self, filing_id: str) -> list[Section]: ...

    def get_section(self, section_id: str) -> Section | None: ...

    def count_filings(self) -> int: ...
