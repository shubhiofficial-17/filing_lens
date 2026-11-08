from __future__ import annotations

import threading

from app.models import Filing, Section


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._filings: dict[str, Filing] = {}
        self._sections: dict[str, list[Section]] = {}

    def add_filing(self, filing: Filing, sections: list[Section]) -> None:
        with self._lock:
            self._filings[filing.id] = filing
            self._sections[filing.id] = list(sections)

    def list_filings(self) -> list[Filing]:
        with self._lock:
            return sorted(self._filings.values(), key=lambda f: (f.ticker, f.fiscal_year))

    def get_filing(self, filing_id: str) -> Filing | None:
        return self._filings.get(filing_id)

    def list_sections(self, filing_id: str) -> list[Section]:
        return list(self._sections.get(filing_id, []))

    def get_section(self, section_id: str) -> Section | None:
        filing_id = section_id.split(":", 1)[0]
        return next((s for s in self._sections.get(filing_id, []) if s.id == section_id), None)

    def count_filings(self) -> int:
        return len(self._filings)
