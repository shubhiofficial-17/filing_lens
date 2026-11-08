"""What the corpus contains: companies, filings and section titles, plus query understanding
(which companies and years a question is about)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import Filing, SearchFilter
from app.store.base import Store
from app.text import years_in

_SUFFIXES = re.compile(r",?\s+(inc\.?|corp\.?|corporation|holdings|ltd\.?|plc|co\.?|llc)\b", re.I)


@dataclass
class Catalog:
    filings: dict[str, Filing]
    companies: dict[str, str]  # ticker -> company name
    titles: dict[str, str]  # section id -> title
    aliases: dict[str, str]  # lower-case alias -> ticker

    @classmethod
    def build(cls, store: Store) -> Catalog:
        filings = {f.id: f for f in store.list_filings()}
        companies: dict[str, str] = {}
        titles: dict[str, str] = {}
        for f in filings.values():
            companies[f.ticker] = f.company
            for s in store.list_sections(f.id):
                titles[s.id] = s.title
        aliases: dict[str, str] = {}
        for ticker, name in companies.items():
            for alias in company_aliases(name):
                aliases[alias] = ticker
            aliases[ticker.lower()] = ticker
        return cls(filings, companies, titles, aliases)

    def company(self, ticker: str) -> str:
        return self.companies.get(ticker, ticker)

    def title(self, section_id: str) -> str:
        return self.titles.get(section_id, "")

    def mentioned_tickers(self, text: str) -> list[str]:
        lowered = f" {text.lower()} "
        found: list[str] = []
        # Longest aliases first, so "northwind robotics" wins over "northwind".
        for alias in sorted(self.aliases, key=len, reverse=True):
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered):
                ticker = self.aliases[alias]
                if ticker not in found:
                    found.append(ticker)
        return found

    def understand(self, question: str) -> SearchFilter:
        """Metadata filters implied by the question. Only years that exist are kept."""
        tickers = tuple(self.mentioned_tickers(question)) or None
        known_years = {f.fiscal_year for f in self.filings.values()}
        years = tuple(y for y in dict.fromkeys(years_in(question)) if y in known_years) or None
        return SearchFilter(tickers=tickers, years=years)


def company_aliases(name: str) -> list[str]:
    """'Northwind Robotics, Inc.' -> ['northwind robotics, inc.', 'northwind robotics',
    'northwind']"""
    full = name.lower().strip()
    base = _SUFFIXES.sub("", name).strip(" ,.").lower()
    out = [full, base]
    first = base.split()[0] if base else ""
    if len(first) > 3:
        out.append(first)
    return list(dict.fromkeys(a for a in out if a))
