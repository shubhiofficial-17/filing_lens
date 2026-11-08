"""DemoLlm: a deterministic stand-in for a language model. It is NOT an AI.

It exists so that the whole system (API, agents, MCP server, evaluation, end-to-end tests)
runs offline and in CI with no API key, and gives the same output every time. It reads the
`TASK:` line of the system prompt and does a simple, rule-based version of that job:

- answer: picks the excerpt sentences that best overlap the question and cites them; uses
  knowledge-graph facts from the notes when they match
- plan: one search per company or year mentioned, or two chained searches for "X, and Y"
- assess: "sufficient" when some excerpt sentence matches the query well

Its answers are extractive and naive on purpose. In particular it will happily repeat
instructions planted in a document, which is exactly what the guardrails must catch.
Numbers reported "in demo mode" measure retrieval and orchestration, not language ability.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.llm.base import Completion, Message, estimate_tokens
from app.models import Usage
from app.rag.prompts import NO_ANSWER
from app.rag.query import GLOSSARY
from app.text import sentences, terms, years_in

_HEADER_RE = re.compile(r"^\[(\d+)\] (.+?) \(([A-Z.]+)\), fiscal (\d{4}), Item (\w+)", re.M)
_TAG_RE = r"<{0}>(.*?)</{0}>"
# The little "world knowledge" the demo model has: the same glossary query rewriting uses
# (CEO = chief executive officer, profit = net income, ...). A real model knows far more.
ABBREVIATIONS = GLOSSARY
QUANTITY = re.compile(r"\b(how much|how many|what was|what percentage|how large)\b", re.I)
MULTI_PART = re.compile(
    r"\b(compare|compared|change|changed|differ|difference|versus|vs\.?|higher|lower|both|"
    r"each|between|from \d{4} to|and who|and what|and how)\b",
    re.I,
)


@dataclass
class Excerpt:
    n: int
    company: str
    ticker: str
    year: int
    item: str
    text: str


def tag(text: str, name: str) -> str:
    m = re.search(_TAG_RE.format(name), text, re.S)
    return m.group(1).strip() if m else ""


def parse_excerpts(block: str) -> list[Excerpt]:
    matches = list(_HEADER_RE.finditer(block))
    out = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        body = block[m.end() : end].split("\n", 1)
        out.append(
            Excerpt(
                n=int(m.group(1)), company=m.group(2), ticker=m.group(3),
                year=int(m.group(4)), item=m.group(5),
                text=body[1].strip() if len(body) > 1 else "",
            )
        )
    return out


def company_key(company: str) -> str:
    return company.split()[0].lower().strip(",.")


class DemoLlm:
    name = "demo (not an AI)"

    def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int = 700,
        json_mode: bool = False,
    ) -> Completion:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = "\n".join(m["content"] for m in messages if m["role"] == "user")
        task = system.split("\n", 1)[0].removeprefix("TASK:").strip()
        handler = getattr(self, f"_task_{task}", None)
        text = handler(user) if handler else ""
        usage = Usage(
            llm_calls=1,
            prompt_tokens=sum(estimate_tokens(m["content"]) for m in messages),
            completion_tokens=estimate_tokens(text),
        )
        return Completion(text=text, model=self.name, usage=usage)

    # --- tasks ---------------------------------------------------------------------------
    def _task_plan(self, user: str) -> str:
        return json.dumps({"steps": plan(tag(user, "question"), tag(user, "corpus"))})

    def _task_route(self, user: str) -> str:
        from app.agents.patterns import COMPLEX_WORDS

        question = tag(user, "question")
        return json.dumps({"route": "complex" if COMPLEX_WORDS.search(question) else "simple"})

    def _task_critique(self, user: str) -> str:
        question, draft = tag(user, "question"), tag(user, "draft")
        found = {e.n: e for e in parse_excerpts(tag(user, "excerpts"))}
        companies = dict(
            (m.group(2), m.group(1))
            for m in re.finditer(r"([^,]+?) \(([A-Z.]+)\)", tag(user, "companies"))
        )
        words = {re.sub(r"'s$", "", w.strip("?,.").lower()) for w in question.split()}
        tickers = [t for t, n in companies.items()
                   if company_key(n.strip()) in words or t.lower() in words]
        years = years_in(question) or [None]
        cited = {(found[int(n)].ticker, found[int(n)].year)
                 for n in re.findall(r"\[(\d+)\]", draft) if int(n) in found}
        missing = [{"ticker": t, "year": y} for t in tickers for y in years
                   if not any(c[0] == t and (y is None or c[1] == y) for c in cited)]
        return json.dumps({"missing": missing, "issues": []})

    def _task_assess(self, user: str) -> str:
        query = tag(user, "question")
        picked = pick_sentences(query, parse_excerpts(tag(user, "excerpts")))
        sufficient = bool(picked) and picked[0][2] >= 3
        return json.dumps({"sufficient": sufficient,
                           "query": "" if sufficient else expand_abbreviations(query)})

    def _task_answer(self, user: str) -> str:
        question = tag(user, "question")
        found = parse_excerpts(tag(user, "excerpts"))
        names = {t for e in found for t in terms(e.company)}
        facts = pick_facts(question, tag(user, "notes"), names)
        # Facts answer part of the question; look for sentences that answer the rest.
        covered = {t for _, f in facts for t in terms(f.split(", per its")[0])}
        picked = pick_sentences(question, found, covered)
        if facts:
            # Facts first; then at most two sentences that add something new.
            known = " ".join(f for _, f in facts).lower()
            picked = [p for p in picked if p[1].lower() not in known][:2]
        if not picked and not facts:
            return NO_ANSWER
        parts = [f"{f.rstrip('.')} [{n}]." for n, f in facts]
        parts += [f"{s.rstrip('.')} [{n}]." for n, s, _ in picked]
        return " ".join(parts)


_FACT_RE = re.compile(r"^- (?P<fact>.+?) \[(?P<n>\d+)\]$", re.M)


def pick_facts(
    question: str, notes: str, ignore: set[str], limit: int = 3
) -> list[tuple[int, str]]:
    """Graph facts from the notes that share at least two terms with the question."""
    q_terms = set(terms(expand_abbreviations(question))) - ignore
    scored = []
    for m in _FACT_RE.finditer(notes):
        fact = m.group("fact")
        overlap = len(q_terms & set(terms(fact.split(", per its")[0])))
        if overlap >= 2:
            scored.append((overlap, int(m.group("n")), fact))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [(n, fact) for _, n, fact in scored[:limit]]


_CORPUS_RE = re.compile(r"^- (?P<name>.+) \((?P<ticker>[A-Z.]+)\)$", re.M)
_CHAIN_RE = re.compile(r"^(?P<a>.+?),? and (?P<b>(?:who|what|how|when|which)\b.+)$", re.I)


def plan(question: str, corpus: str) -> list[dict]:
    companies = {m.group("ticker"): m.group("name") for m in _CORPUS_RE.finditer(corpus)}
    known_years = {int(y) for y in re.findall(r"\b20\d{2}\b", corpus.split("Fiscal years:")[-1])}
    words = {re.sub(r"'s$", "", w.strip("?,.").lower()) for w in question.split()}
    tickers = [t for t, name in companies.items()
               if company_key(name) in words or t.lower() in words]
    years = [y for y in dict.fromkeys(years_in(question)) if y in known_years]

    chain = _CHAIN_RE.match(question)
    if chain and not tickers:
        first, second = chain.group("a").rstrip(" ,"), chain.group("b")
        return [
            {"query": first, "tickers": [], "years": [], "uses_previous": False},
            {"query": second, "tickers": [], "years": years, "uses_previous": True},
        ]
    if len(tickers) > 1:
        return [{"query": question, "tickers": [t], "years": years} for t in tickers]
    if len(years) > 1:
        return [{"query": question, "tickers": tickers, "years": [y]} for y in years]
    return [{"query": question, "tickers": tickers, "years": years}]


def score_sentence(
    question: str, q_terms: set[str], mentioned: set[str], excerpt: Excerpt, sentence: str
) -> float:
    if _is_header_row(sentence):
        return 0.0
    s_terms = set(terms(sentence)) | set(terms(str(excerpt.year)))
    score = float(len(q_terms & s_terms))
    years = years_in(question)
    if years and excerpt.year not in years:
        score *= 0.3
    keys = {company_key(excerpt.company), excerpt.ticker.lower()}
    if mentioned and not keys & mentioned:
        score *= 0.3
    if QUANTITY.search(question) and re.search(r"\d[\d,]*\.\d|\d+%|\d{1,3},\d{3}", sentence):
        score += 1.5
    if sentence.startswith("|"):
        score *= 0.8
    if len(sentence.split()) < 5:
        score *= 0.5
    return score


def expand_abbreviations(text: str) -> str:
    out = text
    for short, long in ABBREVIATIONS.items():
        out = re.sub(rf"(?<![\w&]){re.escape(short)}(?![\w&])", long, out, flags=re.I)
    return out


def mentioned_companies(question: str, found: list[Excerpt]) -> set[str]:
    """Company keys (first word of the name, or ticker) that the question mentions."""
    words = {re.sub(r"'s$", "", w.strip("?,.").lower()) for w in question.split()}
    keys = {company_key(e.company) for e in found} | {e.ticker.lower() for e in found}
    return words & keys


def pick_sentences(
    question: str, found: list[Excerpt], covered: set[str] | None = None
) -> list[tuple[int, str, float]]:
    expanded = expand_abbreviations(question)
    # Company names are matched through the excerpt header, not sentence by sentence;
    # otherwise "X is headquartered in Y" wins every question about X.
    name_terms = {t for e in found for t in terms(e.company)}
    q_terms = set(terms(expanded)) - name_terms
    if covered and len(q_terms - covered) >= 2:
        q_terms -= covered
    mentioned = mentioned_companies(question, found)
    headers = {e.n: _table_header(e.text) for e in found}
    scored: list[tuple[float, int, str, Excerpt]] = []
    for e in found:
        for s in sentences(e.text):
            scored.append((score_sentence(question, q_terms, mentioned, e, s), e.n, s, e))
    scored.sort(key=lambda t: (-t[0], t[1]))
    if not scored or scored[0][0] < 2:
        return []

    def prose(n: int, s: str) -> str:
        return _as_prose(s, headers.get(n))

    best = scored[0]
    picked = [(best[1], prose(best[1], best[2]), best[0])]
    runner_up = next((t for t in scored[1:] if prose(t[1], t[2]) != picked[0][1]), None)
    if runner_up and runner_up[0] >= 0.75 * best[0]:
        picked.append((runner_up[1], prose(runner_up[1], runner_up[2]), runner_up[0]))
    if MULTI_PART.search(question) or len(set(years_in(question))) > 1:
        groups = {(best[3].ticker, best[3].year)}
        for score, n, s, e in scored[1:]:
            if len(picked) >= 4 or score < 0.5 * best[0]:
                break
            text = prose(n, s)
            if (e.ticker, e.year) not in groups and all(text != p[1] for p in picked):
                picked.append((n, text, score))
                groups.add((e.ticker, e.year))
    return picked


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _is_header_row(sentence: str) -> bool:
    return sentence.startswith("|") and all(
        not re.search(r"\d", c) or re.fullmatch(r"(fiscal )?\d{4}", c, re.I)
        for c in _cells(sentence)[1:]
    )


def _table_header(text: str) -> list[str] | None:
    first = text.strip().split("\n", 1)[0]
    return _cells(first) if first.startswith("|") and _is_header_row(first) else None


def _as_prose(sentence: str, header: list[str] | None = None) -> str:
    """'| Revenue | 905.7 | 812.3 |' -> 'Revenue was 905.7 in Fiscal 2024 and 812.3 in ...'"""
    if not sentence.startswith("|"):
        return sentence
    cells = _cells(sentence)
    label, values = cells[0], cells[1:]
    if header and len(header) == len(cells):
        unit = f" ({header[0].strip('()')})" if header[0].startswith("(") else ""
        parts = [f"{v} in {h}" for v, h in zip(values, header[1:], strict=False)]
        return f"{label} was {' and '.join(parts)}{unit}"
    return f"{label}: " + ", ".join(values)
