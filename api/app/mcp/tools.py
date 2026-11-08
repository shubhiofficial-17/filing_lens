"""The tools FilingLens exposes over MCP, as plain functions.

The MCP server (server.py) is a thin wrapper around these, so the same code is used by the
server, the in-app MCP agent's direct mode and the tests. Every tool:
- validates and clamps its inputs (tickers upper-cased, k between 1 and 10, text capped)
- returns JSON-serialisable data with ids that can be cited (chunk ids, filing ids)
- never raises for "not found": it returns {"error": ...} so a model can recover
"""

from __future__ import annotations

import re

from app.models import SearchFilter
from app.rag.pipelines import HybridRag, RagContext
from app.rag.trace import Trace

MAX_TEXT = 6000
METRICS = {
    "revenue": "revenue",
    "net income": "net_income",
    "net income (loss)": "net_income",
    "net loss": "net_income",
    "research and development": "research_and_development",
}


class Tools:
    def __init__(self, ctx: RagContext) -> None:
        self.ctx = ctx

    # --- discovery ---------------------------------------------------------------------
    def list_companies(self) -> dict:
        """Companies and fiscal years available, with the filing id of each 10-K."""
        out: dict[str, dict] = {}
        for f in sorted(self.ctx.catalog.filings.values(), key=lambda f: (f.ticker, f.fiscal_year)):
            entry = out.setdefault(f.ticker, {"ticker": f.ticker, "company": f.company,
                                              "filings": []})
            entry["filings"].append({"filing_id": f.id, "fiscal_year": f.fiscal_year,
                                     "filed_on": f.filed_on})
        return {"companies": list(out.values())}

    # --- retrieval ---------------------------------------------------------------------
    def search_filings(
        self, query: str, tickers: list[str] | None = None, years: list[int] | None = None,
        k: int = 5,
    ) -> dict:
        """Hybrid search (vector + BM25, reranked) over 10-K text and tables."""
        query = (query or "").strip()[:500]
        if not query:
            return {"error": "query is empty"}
        filt = SearchFilter(
            tickers=tuple(t.strip().upper() for t in tickers) if tickers else None,
            years=tuple(int(y) for y in years) if years else None,
        )
        pipeline = HybridRag(RagContext(self.ctx.store, self.ctx.embedder, self.ctx.llm,
                                        top_k=max(1, min(int(k), 10))))
        hits = pipeline.retrieve(query, filt, Trace())
        return {"results": [
            {"chunk_id": h.chunk.id, "company": h.chunk.company, "ticker": h.chunk.ticker,
             "fiscal_year": h.chunk.fiscal_year, "item": h.chunk.item, "kind": h.chunk.kind,
             "score": round(h.score, 4), "text": h.chunk.text}
            for h in hits
        ]}

    def get_section(self, ticker: str, fiscal_year: int, item: str) -> dict:
        """The full text of one Item (e.g. '1A' risk factors) of one 10-K."""
        filing = self._filing(ticker, fiscal_year)
        if filing is None:
            return {"error": f"no 10-K for {ticker} fiscal {fiscal_year}"}
        section = self.ctx.store.get_section(f"{filing.id}:{item.strip().upper()}")
        if section is None:
            items = [s.item for s in self.ctx.store.list_sections(filing.id)]
            return {"error": f"Item {item} not found", "available_items": items}
        text = section.text
        return {"section_id": section.id, "title": section.title,
                "text": text[:MAX_TEXT], "truncated": len(text) > MAX_TEXT}

    def get_financials(self, ticker: str, fiscal_year: int) -> dict:
        """Headline numbers from the income statement table in Item 8 (USD millions)."""
        filing = self._filing(ticker, fiscal_year)
        if filing is None:
            return {"error": f"no 10-K for {ticker} fiscal {fiscal_year}"}
        section = self.ctx.store.get_section(f"{filing.id}:8")
        if section is None:
            return {"error": "no Item 8 in this filing"}
        values = parse_statement(section.text, fiscal_year)
        if not values:
            return {"error": "could not read the income statement table",
                    "section_id": section.id}
        return {"ticker": filing.ticker, "fiscal_year": fiscal_year, "unit": "USD millions",
                "source": section.id, **values}

    def compare_companies(self, tickers: list[str], fiscal_year: int, metric: str) -> dict:
        """One metric (revenue, net_income, research_and_development) across companies."""
        metric = metric.strip().lower().replace(" ", "_")
        rows = []
        for t in tickers[:6]:
            data = self.get_financials(t, fiscal_year)
            rows.append({"ticker": t.upper(), "value": data.get(metric),
                         "source": data.get("source"), "error": data.get("error")})
        ranked = sorted((r for r in rows if r["value"] is not None), key=lambda r: -r["value"])
        return {"metric": metric, "fiscal_year": fiscal_year, "unit": "USD millions",
                "rows": rows, "highest": ranked[0]["ticker"] if ranked else None}

    def graph_lookup(self, text: str) -> dict:
        """Entities named in the text and the facts around them (officers, subsidiaries,
        acquisitions, competitors, customers), each with the chunk it was extracted from."""
        result = self.ctx.graph.expand((text or "")[:500], max_facts=15)
        return {
            "entities": [{"name": e.name, "kind": e.kind} for e in result.mentioned],
            "companies": result.bridge_tickers,
            "facts": [{"fact": f.text(), "relation": f.relation.relation,
                       "chunk_id": f.relation.chunk_id} for f in result.facts],
        }

    def ask(self, question: str, strategy: str = "routed") -> dict:
        """Answer a question end to end with citations (uses the model)."""
        from app.rag.strategies import PIPELINES

        if strategy not in PIPELINES or strategy == "mcp_agent":
            return {"error": f"unknown strategy {strategy}"}
        answer = PIPELINES[strategy](self.ctx).run((question or "").strip()[:500])
        return {
            "answer": answer.text,
            "citations": [{"marker": c.marker, "chunk_id": c.chunk_id, "ticker": c.ticker,
                           "fiscal_year": c.fiscal_year, "item": c.item, "quote": c.quote}
                          for c in answer.citations],
            "strategy": strategy, "model": answer.model,
        }

    def _filing(self, ticker: str, year: int):
        ticker = (ticker or "").strip().upper()
        return next((f for f in self.ctx.catalog.filings.values()
                     if f.ticker == ticker and f.fiscal_year == int(year)), None)


_NUM_RE = re.compile(r"^\(?-?[\d,]+(?:\.\d+)?\)?$")


def parse_statement(text: str, year: int) -> dict:
    """Read '| Revenue | 905.7 | 812.3 |' rows under a '| ... | Fiscal 2024 | ... |' header."""
    out: dict = {}
    column = None
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if column is None:
            for i, c in enumerate(cells):
                if str(year) in c:
                    column = i
            continue
        key = METRICS.get(cells[0].lower())
        if key and column < len(cells) and _NUM_RE.match(cells[column]):
            raw = cells[column]
            value = float(raw.strip("()").replace(",", ""))
            out[key] = -value if raw.startswith("(") else value
    return out


# JSON schemas of the tools, used when the agent calls them directly (without a server).
# Over MCP the agent reads the same information from the server's tools/list.
TOOL_SPECS = [
    {"name": "list_companies", "description": "Companies and fiscal years available.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "search_filings",
     "description": "Hybrid search over 10-K text and tables; returns chunks with chunk_id.",
     "input_schema": {"type": "object", "required": ["query"], "properties": {
         "query": {"type": "string"},
         "tickers": {"type": "array", "items": {"type": "string"}},
         "years": {"type": "array", "items": {"type": "integer"}},
         "k": {"type": "integer", "minimum": 1, "maximum": 10}}}},
    {"name": "get_section", "description": "Full text of one Item of one 10-K.",
     "input_schema": {"type": "object", "required": ["ticker", "fiscal_year", "item"],
                      "properties": {"ticker": {"type": "string"},
                                     "fiscal_year": {"type": "integer"},
                                     "item": {"type": "string"}}}},
    {"name": "get_financials", "description": "Revenue, net income, R&D (USD millions).",
     "input_schema": {"type": "object", "required": ["ticker", "fiscal_year"],
                      "properties": {"ticker": {"type": "string"},
                                     "fiscal_year": {"type": "integer"}}}},
    {"name": "compare_companies", "description": "One metric across companies for a year.",
     "input_schema": {"type": "object", "required": ["tickers", "fiscal_year", "metric"],
                      "properties": {"tickers": {"type": "array", "items": {"type": "string"}},
                                     "fiscal_year": {"type": "integer"},
                                     "metric": {"type": "string"}}}},
    {"name": "graph_lookup",
     "description": "Entities in the text and knowledge-graph facts about them.",
     "input_schema": {"type": "object", "required": ["text"],
                      "properties": {"text": {"type": "string"}}}},
]
AGENT_TOOLS = {"list_companies", "search_filings", "get_section", "get_financials",
               "compare_companies", "graph_lookup"}
