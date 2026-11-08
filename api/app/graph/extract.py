"""Extract a knowledge graph from filing text: companies, organisations, people, and how
they are related (CEO, CFO, OWNS, ACQUIRED, COMPETES_WITH, CUSTOMER, SUCCEEDED).

Two extractors share one output format:
- `RuleExtractor`: patterns for the sentences 10-Ks use for these facts. Deterministic,
  free and precise, but it only knows the phrasings it was written for.
- `LlmExtractor`: asks the model for JSON triples per chunk. It handles any phrasing, at
  the cost of a model call per chunk at ingest time.

Every relation keeps its provenance (filing, fiscal year, chunk), so a graph fact can always
be cited back to the sentence it came from.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from app.llm.base import LlmClient
from app.models import Chunk, Entity, Relation
from app.text import sentences

RELATIONS = ("CEO", "CFO", "OWNS", "ACQUIRED", "COMPETES_WITH", "CUSTOMER", "SUCCEEDED")

# Suffixes dropped from an entity's id ("Bluefin Health Corp." -> "bluefin health"), and the
# longer list dropped for its short alias ("Helix Vision Ltd." -> "helix vision"). Ltd, GmbH
# and friends stay in the id, because they tell a subsidiary from its parent.
_ID_SUFFIX_RE = re.compile(r"[,]?\s+(inc|corp|corporation|co|holdings)\.?$", re.I)
_ALIAS_SUFFIX_RE = re.compile(
    r"[,]?\s+(inc|corp|corporation|co|holdings|ltd|llc|plc|gmbh|k\.k|ltda|sa|ag)\.?$", re.I
)
_NAME = r"[A-Z][\w'&.-]*(?: [A-Z][\w'&.-]*)+"
_PERSON = r"[A-Z][a-z]+(?: [A-Z]\.)?(?: [A-Z][a-z'-]+)+"

_CEO_RE = re.compile(rf"(?P<p>{_PERSON}) serves as our Chief Executive Officer")
_CFO_RE = re.compile(rf"(?P<p>{_PERSON}) serves as our Chief Financial Officer")
_SUBS_RE = re.compile(r"[Oo]ur (?:principal |significant )?subsidiaries (?:are|include) (?P<l>.+)")
_COMP_RE = re.compile(r"[Oo]ur (?:principal |main )?competitors include (?P<l>.+)")
_ACQ_RE = re.compile(
    r"We acquired (?P<o>.+?), an? .+?, in "
    r"(?P<w>(?:[A-Z][a-z]+ )?\d{4})(?: for \$(?P<price>[\d.,]+ (?:million|billion)))?"
)
_CUST_RE = re.compile(r"^(?P<o>[A-Z][\w&.' -]+?) accounted for approximately (?P<pct>\d+)% of our")
_SUCC_RE = re.compile(
    rf"(?P<new>{_PERSON}) was appointed Chief Executive Officer in (?P<w>[A-Z][a-z]+ \d{{4}}), "
    rf"succeeding (?P<old>{_PERSON})"
)


def _strip(name: str, regex: re.Pattern) -> str:
    key = name.strip().rstrip(".")
    for _ in range(2):
        key = regex.sub("", key).strip(" ,.")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9& ]+", "", key.lower())).strip()


def entity_key(name: str) -> str:
    """'Bluefin Health Corp.' -> 'bluefin health'; 'Helix Vision Ltd.' -> 'helix vision ltd'."""
    return _strip(name, _ID_SUFFIX_RE)


def entity_alias(name: str) -> str:
    """The short form people use in questions: 'Helix Vision Ltd.' -> 'helix vision'."""
    return _strip(name, _ALIAS_SUFFIX_RE)


def split_names(listing: str) -> list[str]:
    """'A LLC and B, Inc.' -> ['A LLC', 'B, Inc.']: commas inside names are kept."""
    listing = listing.strip().rstrip(".")
    parts = [p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", listing) if p.strip()]
    out: list[str] = []
    for p in parts:
        if out and re.fullmatch(r"(Inc|Corp|Ltd|LLC|Co|plc)\.?", p, re.I):
            out[-1] = f"{out[-1]}, {p}"
        else:
            out.append(p)
    return [n if n.endswith(".") or not re.search(r"\b(Inc|Ltd|Corp|Co)$", n) else n + "."
            for n in out]


@dataclass
class Extraction:
    entities: list[Entity]
    relations: list[Relation]


class Extractor(Protocol):
    name: str

    def extract(self, company: str, chunks: list[Chunk]) -> Extraction: ...


class _Builder:
    def __init__(self, company: str) -> None:
        self.entities: dict[str, Entity] = {}
        self.relations: list[Relation] = []
        self.company = self.entity(company, "company")

    def entity(self, name: str, kind: str) -> str:
        name = name.strip().rstrip(",")
        key = entity_key(name)
        if key and key not in self.entities:
            self.entities[key] = Entity(id=key, name=name, kind=kind)
        return key

    def relate(self, source: str, relation: str, target: str, chunk: Chunk, detail: str = ""):
        if source and target and source != target:
            self.relations.append(
                Relation(source, relation, target, chunk.filing_id, chunk.fiscal_year, chunk.id,
                         detail)
            )

    def result(self) -> Extraction:
        seen: set[tuple] = set()
        unique = []
        for r in self.relations:
            k = (r.source_id, r.relation, r.target_id, r.filing_id)
            if k not in seen:
                seen.add(k)
                unique.append(r)
        return Extraction(list(self.entities.values()), unique)


class RuleExtractor:
    name = "rules"

    def extract(self, company: str, chunks: list[Chunk]) -> Extraction:
        b = _Builder(company)
        for chunk in chunks:
            if chunk.kind != "text":
                continue
            for s in sentences(chunk.text):
                self._sentence(b, s, chunk)
        return b.result()

    def _sentence(self, b: _Builder, s: str, chunk: Chunk) -> None:
        for regex, relation in ((_CEO_RE, "CEO"), (_CFO_RE, "CFO")):
            m = regex.search(s)
            if m:
                b.relate(b.company, relation, b.entity(m.group("p"), "person"), chunk)
        if m := _SUBS_RE.search(s):
            for name in split_names(m.group("l")):
                b.relate(b.company, "OWNS", b.entity(name, "organization"), chunk)
        if m := _COMP_RE.search(s):
            for name in split_names(m.group("l")):
                b.relate(b.company, "COMPETES_WITH", b.entity(name, "organization"), chunk)
        if m := _ACQ_RE.search(s):
            detail = m.group("w") + (f", ${m.group('price')}" if m.group("price") else "")
            b.relate(b.company, "ACQUIRED", b.entity(m.group("o"), "organization"), chunk,
                     detail)
        if m := _CUST_RE.search(s):
            b.relate(b.company, "CUSTOMER", b.entity(m.group("o"), "organization"), chunk,
                     f"{m.group('pct')}% of revenue")
        if m := _SUCC_RE.search(s):
            new, old = b.entity(m.group("new"), "person"), b.entity(m.group("old"), "person")
            b.relate(new, "SUCCEEDED", old, chunk, f"as Chief Executive Officer, {m.group('w')}")


class LlmExtractor:
    """One model call per text chunk; the reply must be JSON triples."""

    name = "llm"

    def __init__(self, llm: LlmClient, model: str | None = None) -> None:
        self._llm = llm
        self._model = model

    def extract(self, company: str, chunks: list[Chunk]) -> Extraction:
        from app.graph.prompts import extract_messages

        b = _Builder(company)
        for chunk in chunks:
            if chunk.kind != "text":
                continue
            reply = self._llm.complete(
                extract_messages(company, chunk.text), model=self._model, json_mode=True
            )
            for t in parse_triples(reply.text):
                source = b.company if t["source"] == "COMPANY" else b.entity(
                    t["source"], t.get("source_kind", "organization"))
                target = b.entity(t["target"], t.get("target_kind", "organization"))
                b.relate(source, t["relation"], target, chunk, t.get("detail", ""))
        return b.result()


def parse_triples(text: str) -> list[dict]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0)).get("triples", [])
    except (ValueError, AttributeError):
        return []
    out = []
    for t in items:
        if (isinstance(t, dict) and t.get("relation") in RELATIONS
                and isinstance(t.get("source"), str) and isinstance(t.get("target"), str)):
            out.append(t)
    return out
