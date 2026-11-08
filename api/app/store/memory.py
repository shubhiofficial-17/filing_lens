from __future__ import annotations

import threading

from app.models import Chunk, Filing, Hit, SearchFilter, Section
from app.rag.embeddings import cosine


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._filings: dict[str, Filing] = {}
        self._sections: dict[str, list[Section]] = {}
        self._chunks: dict[str, Chunk] = {}
        self._index_text: dict[str, str] = {}
        self._vectors: dict[str, list[float]] = {}

    def add_filing(self, filing: Filing, sections: list[Section]) -> None:
        with self._lock:
            self._drop_chunks(filing.id)
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

    # --- chunks ---------------------------------------------------------------------
    def add_chunks(
        self, chunks: list[Chunk], index_texts: list[str], vectors: list[list[float]]
    ) -> None:
        with self._lock:
            for chunk, text, vec in zip(chunks, index_texts, vectors, strict=True):
                self._chunks[chunk.id] = chunk
                self._index_text[chunk.id] = text
                self._vectors[chunk.id] = vec

    def _drop_chunks(self, filing_id: str) -> None:
        for cid in [c.id for c in self._chunks.values() if c.filing_id == filing_id]:
            self._chunks.pop(cid, None)
            self._index_text.pop(cid, None)
            self._vectors.pop(cid, None)

    def count_chunks(self) -> int:
        return len(self._chunks)

    def get_chunks(self, ids: list[str]) -> list[Chunk]:
        return [self._chunks[i] for i in ids if i in self._chunks]

    def vector_search(
        self, vector: list[float], k: int, filt: SearchFilter | None = None
    ) -> list[Hit]:
        filt = filt or SearchFilter()
        with self._lock:
            scored = [
                (cosine(vector, self._vectors[cid]), cid)
                for cid, chunk in self._chunks.items()
                if filt.allows(chunk)
            ]
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [Hit(self._chunks[cid], score, "vector") for score, cid in scored[:k]]
