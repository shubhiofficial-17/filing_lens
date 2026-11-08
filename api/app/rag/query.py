"""Query understanding: rewrite the question into the vocabulary filings actually use.

People ask about "the CEO" and "R&D"; 10-Ks say "Chief Executive Officer" and "research and
development". A short domain glossary closes most of that gap at no cost. The agentic
strategy can also ask the model for rewrites.
"""

from __future__ import annotations

import re

GLOSSARY: dict[str, str] = {
    "ceo": "chief executive officer",
    "cfo": "chief financial officer",
    "coo": "chief operating officer",
    "r&d": "research and development",
    "md&a": "management's discussion and analysis",
    "headcount": "full-time employees",
    "staff": "employees",
    "workforce": "employees",
    "profit": "net income",
    "profitability": "net income",
    "earnings": "net income",
    "sales": "revenue",
    "top line": "revenue",
    "biggest customer": "largest customer accounted for revenue",
    "largest customer": "customer accounted for revenue",
    "owns": "subsidiaries",
    "subsidiary": "subsidiaries",
    "rivals": "competitors",
    "competition": "competitors",
    "acquire": "acquired",
    "bought": "acquired",
    "hack": "cybersecurity breach",
    "risks": "risk factors",
}


def rewrite(question: str) -> str:
    """The question plus glossary expansions (the original words are kept for BM25)."""
    additions: list[str] = []
    lowered = question.lower()
    for short, long in GLOSSARY.items():
        if re.search(rf"(?<![\w&]){re.escape(short)}(?![\w&])", lowered):
            additions.append(long)
    if not additions:
        return question
    return f"{question} ({'; '.join(dict.fromkeys(additions))})"
