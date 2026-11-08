"""PostgreSQL store. Plain SQL through psycopg 3 and a connection pool."""

from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.models import Filing, Section

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS filings (
    id          text PRIMARY KEY,
    ticker      text NOT NULL,
    company     text NOT NULL,
    cik         text NOT NULL,
    fiscal_year int  NOT NULL,
    form        text NOT NULL,
    filed_on    text NOT NULL DEFAULT '',
    source_url  text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS filings_ticker_year ON filings (ticker, fiscal_year);

CREATE TABLE IF NOT EXISTS sections (
    id         text PRIMARY KEY,
    filing_id  text NOT NULL REFERENCES filings (id) ON DELETE CASCADE,
    item       text NOT NULL,
    title      text NOT NULL,
    text       text NOT NULL,
    position   int  NOT NULL
);
CREATE INDEX IF NOT EXISTS sections_filing ON sections (filing_id, position);
"""


class PostgresStore:
    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        self._pool = ConnectionPool(url, min_size=min_size, max_size=max_size, open=False)

    # --- lifecycle --------------------------------------------------------------------
    def open(self) -> None:
        self._pool.open(wait=True, timeout=30)
        with self._pool.connection() as conn:
            # Two app instances starting at once must not race on CREATE TABLE.
            conn.execute("SELECT pg_advisory_lock(7201)")
            try:
                conn.execute(self.schema())
            finally:
                conn.execute("SELECT pg_advisory_unlock(7201)")

    def close(self) -> None:
        self._pool.close()

    def schema(self) -> str:
        return SCHEMA

    def pgvector_version(self) -> str | None:
        with self._pool.connection(timeout=2) as conn:
            row = conn.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
            return row[0] if row else None

    def reset(self) -> None:
        """Delete everything. Used by tests."""
        with self._pool.connection() as conn:
            conn.execute("TRUNCATE filings CASCADE")

    # --- filings and sections --------------------------------------------------------
    def add_filing(self, filing: Filing, sections: list[Section]) -> None:
        with self._pool.connection() as conn, conn.transaction():
            conn.execute("DELETE FROM filings WHERE id = %s", (filing.id,))
            conn.execute(
                "INSERT INTO filings (id, ticker, company, cik, fiscal_year, form, filed_on,"
                " source_url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (filing.id, filing.ticker, filing.company, filing.cik, filing.fiscal_year,
                 filing.form, filing.filed_on, filing.source_url),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO sections (id, filing_id, item, title, text, position)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    [(s.id, s.filing_id, s.item, s.title, s.text, n)
                     for n, s in enumerate(sections)],
                )

    def list_filings(self) -> list[Filing]:
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute("SELECT * FROM filings ORDER BY ticker, fiscal_year").fetchall()
        return [_filing(r) for r in rows]

    def get_filing(self, filing_id: str) -> Filing | None:
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute("SELECT * FROM filings WHERE id = %s", (filing_id,)).fetchone()
        return _filing(row) if row else None

    def list_sections(self, filing_id: str) -> list[Section]:
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM sections WHERE filing_id = %s ORDER BY position", (filing_id,)
            ).fetchall()
        return [_section(r) for r in rows]

    def get_section(self, section_id: str) -> Section | None:
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute("SELECT * FROM sections WHERE id = %s", (section_id,)).fetchone()
        return _section(row) if row else None

    def count_filings(self) -> int:
        with self._pool.connection() as conn:
            return conn.execute("SELECT count(*) FROM filings").fetchone()[0]

    # --- shared helpers for subclasses -------------------------------------------------
    @property
    def pool(self) -> ConnectionPool:
        return self._pool


def _filing(r: dict) -> Filing:
    return Filing(
        id=r["id"], ticker=r["ticker"], company=r["company"], cik=r["cik"],
        fiscal_year=r["fiscal_year"], form=r["form"], filed_on=r["filed_on"],
        source_url=r["source_url"],
    )


def _section(r: dict) -> Section:
    return Section(id=r["id"], filing_id=r["filing_id"], item=r["item"], title=r["title"],
                   text=r["text"])
