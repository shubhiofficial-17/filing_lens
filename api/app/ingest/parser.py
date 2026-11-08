"""Turn a 10-K HTML document into Sections (one per Item).

EDGAR documents are messy: inline XBRL, hidden header blocks, tables used for layout, a table
of contents that repeats every Item heading, and dollar signs in their own table cells. The
parser keeps two kinds of blocks (paragraphs and tables), finds the Item headings, and when an
Item heading appears more than once (table of contents, page headers) keeps the occurrence
followed by the most text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from app.models import Section

_BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
    "body", "br", "hr", "title", "center", "blockquote",
}
_SKIP_TAGS = {"script", "style", "head", "ix:header"}
_ITEM_RE = re.compile(r"^item\s+(\d{1,2}[a-c]?)\s*[.:\-–—]?\s*(.*)$", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


@dataclass
class Block:
    kind: str  # "text" | "table"
    text: str


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._text: list[str] = []
        self._skip: list[str] = []  # tag names we are skipping inside
        self._table_depth = 0
        self._rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    # --- helpers -----------------------------------------------------------------
    def _flush_text(self) -> None:
        text = _clean("".join(self._text))
        self._text = []
        if text:
            self.blocks.append(Block("text", text))

    def _end_cell(self) -> None:
        if self._cell is not None and self._row is not None:
            self._row.append(_clean("".join(self._cell)))
        self._cell = None

    def _end_row(self) -> None:
        self._end_cell()
        if self._row is not None:
            cells = _merge_cells(self._row)
            if cells:
                self._rows.append(cells)
        self._row = None

    # --- HTMLParser hooks ----------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.append(tag)
            return
        style = (dict(attrs).get("style") or "").replace(" ", "").lower()
        if tag in _SKIP_TAGS or "display:none" in style:
            self._skip.append(tag)
            return
        if tag == "table":
            if self._table_depth == 0:
                self._flush_text()
                self._rows = []
            self._table_depth += 1
        elif self._table_depth and tag == "tr":
            self._end_row()
            self._row = []
        elif self._table_depth and tag in ("td", "th"):
            self._end_cell()
            if self._row is None:
                self._row = []
            self._cell = []
        elif not self._table_depth and tag in _BLOCK_TAGS:
            self._flush_text()

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.pop()
            return
        if self._table_depth:
            if tag in ("td", "th"):
                self._end_cell()
            elif tag == "tr":
                self._end_row()
            elif tag == "table":
                self._table_depth -= 1
                if self._table_depth == 0:
                    self._end_row()
                    self._emit_table()
        elif tag in _BLOCK_TAGS:
            self._flush_text()

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._table_depth:
            if self._cell is not None:
                self._cell.append(data)
        else:
            self._text.append(data)

    def close(self) -> None:
        super().close()
        self._flush_text()

    def _emit_table(self) -> None:
        rows = self._rows
        self._rows = []
        if not rows:
            return
        # A one-cell-per-row table is layout, not data: treat each row as a paragraph.
        if all(len(r) == 1 for r in rows):
            for r in rows:
                self.blocks.append(Block("text", r[0]))
            return
        lines = ["| " + " | ".join(r) + " |" for r in rows]
        self.blocks.append(Block("table", "\n".join(lines)))


def _clean(text: str) -> str:
    return _SPACE_RE.sub(" ", text.replace("\xa0", " ")).strip()


def _merge_cells(cells: list[str]) -> list[str]:
    """Drop empty cells and glue '$', ')' and '%' cells to their neighbours."""
    out: list[str] = []
    pending_prefix = ""
    for cell in cells:
        if not cell:
            continue
        if cell in ("$", "(", "($"):
            pending_prefix += cell.replace("$", "")
            continue
        if cell in (")", "%", ")%") and out:
            out[-1] += cell
            continue
        out.append(pending_prefix + cell)
        pending_prefix = ""
    return out


def html_to_blocks(html: str) -> list[Block]:
    collector = _Collector()
    collector.feed(html)
    collector.close()
    return collector.blocks


def split_items(blocks: list[Block]) -> list[tuple[str, str, list[Block]]]:
    """Group blocks under Item headings. Returns (item, title, blocks) in document order."""
    headings: list[tuple[int, str, str]] = []
    for i, block in enumerate(blocks):
        if block.kind != "text" or len(block.text) > 150:
            continue
        m = _ITEM_RE.match(block.text)
        if m:
            headings.append((i, m.group(1).upper(), m.group(2).strip(" .")))

    best: dict[str, tuple[int, str, list[Block], int]] = {}
    for n, (index, item, title) in enumerate(headings):
        end = headings[n + 1][0] if n + 1 < len(headings) else len(blocks)
        body = blocks[index + 1 : end]
        words = sum(len(b.text.split()) for b in body)
        if item not in best or words > best[item][3]:
            best[item] = (index, title, body, words)

    ordered = sorted(best.items(), key=lambda kv: kv[1][0])
    return [(item, title, body) for item, (_, title, body, words) in ordered if words > 0]


def parse_filing_html(html: str, filing_id: str) -> list[Section]:
    sections: list[Section] = []
    for item, title, body in split_items(html_to_blocks(html)):
        text = "\n\n".join(b.text for b in body)
        sections.append(
            Section(
                id=f"{filing_id}:{item}",
                filing_id=filing_id,
                item=item,
                title=title or f"Item {item}",
                text=text,
            )
        )
    return sections
