"""PostgreSQL store. Plain SQL through psycopg 3 and a connection pool."""

from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.models import Chunk, Filing, Hit, SearchFilter, Section

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

CREATE TABLE IF NOT EXISTS chunks (
    id          text PRIMARY KEY,
    section_id  text NOT NULL REFERENCES sections (id) ON DELETE CASCADE,
    filing_id   text NOT NULL REFERENCES filings (id) ON DELETE CASCADE,
    ticker      text NOT NULL,
    fiscal_year int  NOT NULL,
    item        text NOT NULL,
    kind        text NOT NULL,
    position    int  NOT NULL,
    text        text NOT NULL,
    index_text  text NOT NULL,
    embedding   vector({dim}) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_filter ON chunks (ticker, fiscal_year, item);
CREATE INDEX IF NOT EXISTS chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
"""

_CHUNK_COLS = "id, section_id, filing_id, ticker, fiscal_year, item, text, kind"


class PostgresStore:
    def __init__(self, url: str, *, dim: int = 256, min_size: int = 1, max_size: int = 10) -> None:
        self._dim = dim
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
        return SCHEMA.format(dim=self._dim)

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

    # --- chunks ---------------------------------------------------------------------
    def add_chunks(
        self, chunks: list[Chunk], index_texts: list[str], vectors: list[list[float]]
    ) -> None:
        rows = [
            (c.id, c.section_id, c.filing_id, c.ticker, c.fiscal_year, c.item, c.kind, n, c.text,
             text, _vector(vec))
            for n, (c, text, vec) in enumerate(zip(chunks, index_texts, vectors, strict=True))
        ]
        with self._pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (id, section_id, filing_id, ticker, fiscal_year, item, kind,"
                " position, text, index_text, embedding)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)"
                " ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text,"
                " index_text = EXCLUDED.index_text, embedding = EXCLUDED.embedding",
                rows,
            )

    def count_chunks(self) -> int:
        with self._pool.connection() as conn:
            return conn.execute("SELECT count(*) FROM chunks").fetchone()[0]

    def get_chunks(self, ids: list[str]) -> list[Chunk]:
        if not ids:
            return []
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"SELECT {_CHUNK_COLS} FROM chunks WHERE id = ANY(%s)", (list(ids),)
            ).fetchall()
        by_id = {r["id"]: _chunk(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def vector_search(
        self, vector: list[float], k: int, filt: SearchFilter | None = None
    ) -> list[Hit]:
        where, params = _where(filt)
        params["q"] = _vector(vector)
        params["k"] = k
        sql = (
            f"SELECT {_CHUNK_COLS}, 1 - (embedding <=> %(q)s::vector) AS score FROM chunks"
            f" WHERE {where} ORDER BY embedding <=> %(q)s::vector, id LIMIT %(k)s"
        )
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            # Filtered HNSW scans can stop before finding k matches; scan further when needed.
            cur.execute("SET LOCAL hnsw.ef_search = 100")
            rows = cur.execute(sql, params).fetchall()
        return [Hit(_chunk(r), float(r["score"]), "vector") for r in rows]

    # --- shared helpers --------------------------------------------------------------
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


def _chunk(r: dict) -> Chunk:
    return Chunk(id=r["id"], section_id=r["section_id"], filing_id=r["filing_id"],
                 ticker=r["ticker"], fiscal_year=r["fiscal_year"], item=r["item"],
                 text=r["text"], kind=r["kind"])


def _vector(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def _where(filt: SearchFilter | None) -> tuple[str, dict]:
    filt = filt or SearchFilter()
    clauses = ["true"]
    params: dict = {}
    if filt.tickers:
        clauses.append("ticker = ANY(%(tickers)s)")
        params["tickers"] = list(filt.tickers)
    if filt.years:
        clauses.append("fiscal_year = ANY(%(years)s)")
        params["years"] = list(filt.years)
    if filt.items:
        clauses.append("item = ANY(%(items)s)")
        params["items"] = list(filt.items)
    return " AND ".join(clauses), params
