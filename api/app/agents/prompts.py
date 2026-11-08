from __future__ import annotations

from app.models import Hit
from app.rag.catalog import Catalog
from app.rag.prompts import DATA_RULE, excerpts

PLAN_SYSTEM = """TASK: plan
You plan the searches needed to answer a question about SEC 10-K filings.
Break the question into at most 4 search steps. Each step searches one company and/or
fiscal year when the question compares several, so every side gets its own evidence.
If a step needs the result of the previous step (for example "that company's CEO"), set
"uses_previous": true and leave its tickers empty.
Only use tickers and years listed in <corpus>. Reply with JSON only:
{"steps": [{"query": "...", "tickers": ["ABC"], "years": [2024], "uses_previous": false}]}"""

ASSESS_SYSTEM = f"""TASK: assess
Decide whether the excerpts contain enough to answer the search query.
If not, suggest a better search query using the vocabulary a 10-K would use.
Reply with JSON only: {{"sufficient": true, "query": ""}}
{DATA_RULE}"""


def corpus_block(catalog: Catalog) -> str:
    companies = "\n".join(f"- {name} ({t})" for t, name in sorted(catalog.companies.items()))
    years = ", ".join(str(y) for y in sorted({f.fiscal_year for f in catalog.filings.values()}))
    return f"<corpus>\nCompanies:\n{companies}\nFiscal years: {years}\n</corpus>"


def plan_messages(question: str, catalog: Catalog) -> list[dict[str, str]]:
    user = f"<question>{question}</question>\n{corpus_block(catalog)}"
    return [{"role": "system", "content": PLAN_SYSTEM}, {"role": "user", "content": user}]


def assess_messages(query: str, hits: list[Hit], catalog: Catalog) -> list[dict[str, str]]:
    user = f"<question>{query}</question>\n<excerpts>\n{excerpts(hits, catalog)}\n</excerpts>"
    return [{"role": "system", "content": ASSESS_SYSTEM}, {"role": "user", "content": user}]
