"""Domain records shared by ingestion, retrieval, agents and the API.

They are plain dataclasses on purpose: the retrieval and agent code has no web or database
dependency, so it runs (and is tested) the same way in the API, the MCP server and the
evaluation runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Filing:
    id: str  # e.g. "NWRB-2024-10K", or the EDGAR accession number
    ticker: str
    company: str
    cik: str
    fiscal_year: int
    form: str = "10-K"
    filed_on: str = ""  # ISO date
    source_url: str = ""


@dataclass(frozen=True)
class Section:
    """One Item of a 10-K (Item 1, 1A, 7, 8, ...). Tables are kept as lines starting with '|'."""

    id: str  # "{filing_id}:{item}"
    filing_id: str
    item: str  # "1", "1A", "7", ...
    title: str
    text: str


@dataclass(frozen=True)
class Chunk:
    id: str  # "{section_id}#{n}"
    section_id: str
    filing_id: str
    ticker: str
    fiscal_year: int
    item: str
    text: str
    kind: str = "text"  # "text" | "table"


@dataclass(frozen=True)
class SearchFilter:
    tickers: tuple[str, ...] | None = None
    years: tuple[int, ...] | None = None
    items: tuple[str, ...] | None = None

    def allows(self, chunk: Chunk) -> bool:
        if self.tickers and chunk.ticker not in self.tickers:
            return False
        if self.years and chunk.fiscal_year not in self.years:
            return False
        if self.items and chunk.item not in self.items:
            return False
        return True


@dataclass
class Hit:
    chunk: Chunk
    score: float
    source: str  # "vector" | "bm25" | "hybrid" | "rerank" | "graph"


@dataclass(frozen=True)
class Entity:
    id: str  # normalised name key
    name: str
    kind: str  # "company" | "organization" | "person"


@dataclass(frozen=True)
class Relation:
    source_id: str
    relation: str  # CEO | CFO | OWNS | ACQUIRED | COMPETES_WITH | CUSTOMER
    target_id: str
    filing_id: str
    fiscal_year: int
    chunk_id: str
    detail: str = ""


@dataclass(frozen=True)
class Citation:
    marker: int
    chunk_id: str
    filing_id: str
    ticker: str
    fiscal_year: int
    item: str
    quote: str
    supported: bool = True


@dataclass
class TraceStep:
    name: str
    detail: str = ""
    data: dict = field(default_factory=dict)
    ms: float = 0.0


@dataclass
class Usage:
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: Usage) -> None:
        self.llm_calls += other.llm_calls
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cost_usd += other.cost_usd


@dataclass
class Answer:
    question: str
    strategy: str
    text: str
    citations: list[Citation] = field(default_factory=list)
    retrieved: list[Hit] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    latency_ms: float = 0.0
