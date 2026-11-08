"""Split sections into chunks for retrieval.

- Paragraphs are grouped up to `max_words`; a paragraph is never cut unless it alone is too
  long (then it is split on sentence boundaries).
- Tables are never split and never mixed with prose: a table chunk keeps every row with its
  header row, so a number is always retrieved together with its label and year columns.
- Every chunk gets a contextual header (company, ticker, fiscal year, Item and title) that is
  embedded and indexed with it. A paragraph like "Revenue grew 11.5%" says nothing about
  *whose* revenue or *which* year; the header does.
"""

from __future__ import annotations

from app.models import Chunk, Filing, Section
from app.text import sentences

MAX_WORDS = 80


def chunk_section(section: Section, filing: Filing, max_words: int = MAX_WORDS) -> list[Chunk]:
    pieces: list[tuple[str, str]] = []  # (kind, text)
    buffer: list[str] = []
    words = 0

    def flush() -> None:
        nonlocal buffer, words
        if buffer:
            pieces.append(("text", "\n\n".join(buffer)))
        buffer, words = [], 0

    for para in (p.strip() for p in section.text.split("\n\n")):
        if not para:
            continue
        if para.startswith("|"):
            flush()
            pieces.append(("table", para))
            continue
        n = len(para.split())
        if _is_heading(para) and words > max_words * 0.6:
            flush()  # keep a sub-heading with the paragraph it introduces
        if n > max_words:
            flush()
            for part in _split_long(para, max_words):
                pieces.append(("text", part))
            continue
        if words + n > max_words:
            flush()
        buffer.append(para)
        words += n
    flush()

    return [
        Chunk(
            id=f"{section.id}#{i}",
            section_id=section.id,
            filing_id=filing.id,
            ticker=filing.ticker,
            fiscal_year=filing.fiscal_year,
            item=section.item,
            text=text,
            kind=kind,
            company=filing.company,
        )
        for i, (kind, text) in enumerate(pieces)
    ]


def _is_heading(paragraph: str) -> bool:
    return len(paragraph.split()) <= 12 and not paragraph.rstrip().endswith((".", ":", ";"))


def _split_long(paragraph: str, max_words: int) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    count = 0
    for s in sentences(paragraph):
        n = len(s.split())
        if current and count + n > max_words:
            out.append(" ".join(current))
            current, count = [], 0
        current.append(s)
        count += n
    if current:
        out.append(" ".join(current))
    return out


def context_header(chunk: Chunk, company: str, title: str) -> str:
    return f"{company} ({chunk.ticker}) 10-K fiscal {chunk.fiscal_year}, Item {chunk.item} {title}"


def index_text(chunk: Chunk, company: str, title: str) -> str:
    """What gets embedded and keyword-indexed: the header plus the chunk text."""
    return f"{context_header(chunk, company, title)}\n{chunk.text}"
