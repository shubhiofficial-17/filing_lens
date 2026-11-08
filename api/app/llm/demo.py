"""DemoLlm: a deterministic stand-in for a language model. It is NOT an AI.

It exists so that the whole system (API, agents, MCP server, evaluation, end-to-end tests)
runs offline and in CI with no API key, and gives the same output every time. It reads the
`TASK:` line of the system prompt and does a simple, rule-based version of that job:

- answer: picks the excerpt sentences that best overlap the question and cites them
- other tasks are added by later milestones

Its answers are extractive and naive on purpose. In particular it will happily repeat
instructions planted in a document, which is exactly what the guardrails must catch.
Numbers reported "in demo mode" measure retrieval and orchestration, not language ability.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.llm.base import Completion, Message, estimate_tokens
from app.models import Usage
from app.rag.prompts import NO_ANSWER
from app.text import sentences, terms, years_in

_HEADER_RE = re.compile(r"^\[(\d+)\] (.+?) \(([A-Z.]+)\), fiscal (\d{4}), Item (\w+)", re.M)
_TAG_RE = r"<{0}>(.*?)</{0}>"
# The little "world knowledge" the demo model has: common abbreviations in filings.
ABBREVIATIONS = {
    "ceo": "chief executive officer",
    "cfo": "chief financial officer",
    "r&d": "research and development",
    "md&a": "management's discussion and analysis",
}
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
    def _task_answer(self, user: str) -> str:
        question = tag(user, "question")
        found = parse_excerpts(tag(user, "excerpts"))
        picked = pick_sentences(question, found)
        if not picked:
            return NO_ANSWER
        return " ".join(f"{s.rstrip('.')} [{n}]." for n, s, _ in picked)


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


def pick_sentences(question: str, found: list[Excerpt]) -> list[tuple[int, str, float]]:
    expanded = expand_abbreviations(question)
    # Company names are matched through the excerpt header, not sentence by sentence;
    # otherwise "X is headquartered in Y" wins every question about X.
    name_terms = {t for e in found for t in terms(e.company)}
    q_terms = set(terms(expanded)) - name_terms
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
    if MULTI_PART.search(question) or len(set(years_in(question))) > 1:
        groups = {(best[3].ticker, best[3].year)}
        for score, n, s, e in scored[1:]:
            if len(picked) >= 3 or score < 0.5 * best[0]:
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
