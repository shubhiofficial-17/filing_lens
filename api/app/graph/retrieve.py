"""Answer-time use of the graph: find the entities a question mentions, collect the facts
around them, and follow one more hop through the companies those facts lead to.

"Which company owns Helix Vision Ltd., and who was that company's CEO?" has no company
name for a search filter. The graph turns "Helix Vision" into "owned by Northwind Robotics",
and the second hop finds Northwind's CEO. Text search alone has to get lucky twice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.graph.extract import entity_alias, entity_key
from app.models import Entity, Relation
from app.rag.catalog import Catalog
from app.store.base import Store
from app.text import terms, years_in

# Words in a question that point at a relation type.
RELATION_HINTS: dict[str, tuple[str, ...]] = {
    "CEO": ("ceo", "chief executive"),
    "CFO": ("cfo", "chief financial"),
    "OWNS": ("own", "subsidiar", "parent"),
    "ACQUIRED": ("acquir", "bought", "purchase", "pay"),
    "COMPETES_WITH": ("compet", "rival"),
    "CUSTOMER": ("customer", "client", "payer"),
    "SUCCEEDED": ("succeed", "predecessor", "replace"),
}


@dataclass(frozen=True)
class Fact:
    relation: Relation
    source: Entity
    target: Entity
    hop: int

    def text(self) -> str:
        s, t, r = self.source.name, self.target.name, self.relation
        detail = f" ({r.detail})" if r.detail else ""
        phrases = {
            "CEO": f"{t} is the Chief Executive Officer of {s}",
            "CFO": f"{t} is the Chief Financial Officer of {s}",
            "OWNS": f"{s} owns {t}",
            "ACQUIRED": f"{s} acquired {t}{detail}",
            "COMPETES_WITH": f"{s} lists {t} as a competitor",
            "CUSTOMER": f"{t} is a major customer of {s}{detail}",
            "SUCCEEDED": f"{s} succeeded {t}{detail}",
        }
        sentence = phrases.get(r.relation, f"{s} {r.relation} {t}")
        return f"{sentence}, per its fiscal {r.fiscal_year} annual report"


@dataclass
class GraphResult:
    mentioned: list[Entity]
    facts: list[Fact]
    bridge_tickers: list[str]


class Graph:
    def __init__(self, store: Store, catalog: Catalog) -> None:
        self._store = store
        self._entities = {e.id: e for e in store.list_entities()}
        self._ticker_by_entity = {entity_key(name): t for t, name in catalog.companies.items()}
        # Aliases: id and short form. A short form that collides with another entity's id
        # ("northwind robotics" for "Northwind Robotics GmbH") is not used.
        aliases: dict[str, str] = {}
        for e in self._entities.values():
            aliases[e.id] = e.id
        for e in self._entities.values():
            alias = entity_alias(e.name)
            if alias and alias not in aliases:
                aliases[alias] = e.id
        self._aliases = aliases

    def mentions(self, text: str) -> list[Entity]:
        lowered = " " + re.sub(r"[^a-z0-9& ]+", " ", text.lower()) + " "
        lowered = re.sub(r"\s+", " ", lowered)
        found: list[str] = []
        taken: list[tuple[int, int]] = []
        for alias in sorted(self._aliases, key=len, reverse=True):
            for m in re.finditer(rf" {re.escape(alias)} ", lowered):
                span = (m.start(), m.end())
                if any(a < span[1] and span[0] < b for a, b in taken):
                    continue  # part of a longer name already matched
                taken.append(span)
                eid = self._aliases[alias]
                if eid not in found:
                    found.append(eid)
        return [self._entities[e] for e in found]

    def ticker(self, entity_id: str) -> str | None:
        return self._ticker_by_entity.get(entity_id)

    def expand(self, question: str, max_facts: int = 8) -> GraphResult:
        mentioned = self.mentions(question)
        ids = [e.id for e in mentioned]
        wanted = wanted_relations(question)
        years = set(years_in(question))

        hop1 = [self._fact(r, 1) for r in self._store.relations_for(ids)]
        bridges = {f.source.id for f in hop1 if self.ticker(f.source.id)}
        bridges |= {e.id for e in mentioned if self.ticker(e.id)}
        hop2: list[Fact] = []
        if wanted:
            seen = {(f.relation.source_id, f.relation.relation, f.relation.target_id,
                     f.relation.filing_id) for f in hop1}
            for r in self._store.relations_for(sorted(bridges)):
                key = (r.source_id, r.relation, r.target_id, r.filing_id)
                if r.relation in wanted and key not in seen:
                    hop2.append(self._fact(r, 2))

        def rank(f: Fact) -> tuple:
            return (
                f.relation.relation not in wanted,  # relations the question asks about first
                bool(years) and f.relation.fiscal_year not in years,  # then the asked years
                f.hop,
                -f.relation.fiscal_year,  # newest first
                f.text(),
            )

        # Keep facts the question is about: a relation it asks for, or an entity it names
        # that isn't simply the filing company (whose every fact would match).
        named = {e.id for e in mentioned if not self.ticker(e.id)}
        relevant = [
            f for f in hop1 + hop2
            if f.relation.relation in wanted or {f.source.id, f.target.id} & named
        ]
        facts = _dedupe(sorted(relevant, key=rank), years)[:max_facts]
        tickers = [t for b in sorted(bridges) if (t := self.ticker(b))]
        return GraphResult(mentioned, facts, tickers)

    def _fact(self, r: Relation, hop: int) -> Fact:
        return Fact(r, self._entities[r.source_id], self._entities[r.target_id], hop)


def wanted_relations(question: str) -> set[str]:
    q = " ".join(terms(question)) + " " + question.lower()
    return {rel for rel, hints in RELATION_HINTS.items() if any(h in q for h in hints)}


def _dedupe(facts: list[Fact], years: set[int]) -> list[Fact]:
    """The same fact from several years: keep the best-ranked one, or one per year asked."""
    out, seen = [], set()
    for f in facts:
        year = f.relation.fiscal_year if f.relation.fiscal_year in years else None
        key = (f.relation.source_id, f.relation.relation, f.relation.target_id, year)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out
