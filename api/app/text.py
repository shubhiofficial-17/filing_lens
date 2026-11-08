"""Small, dependency-free text helpers: tokens, terms for search, sentences."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?%?|[a-z]+(?:'[a-z]+)?")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"(])")

STOPWORDS = frozenset(
    """a an and are as at be been being but by did do does for from had has have how in into is it
    its of on or our over than that the their them then there these they this those to was were what
    when where which who whom whose why will with would we us you your about after again against all
    also any because before between both can could during each few further here if more most other
    own same should so some such through under until up very while according fiscal year years
    company company's report reported describe described say said 10-k form""".split()
)


def tokens(text: str) -> list[str]:
    """Lower-cased words and numbers. '1,486.2' and '18%' stay single tokens."""
    return _TOKEN_RE.findall(text.lower().replace("’", "'"))


def stem(word: str) -> str:
    """A deliberately tiny stemmer: enough to match plurals and possessives."""
    if word.endswith("'s"):
        word = word[:-2]
    if word[0].isdigit():
        return word.replace(",", "")
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def terms(text: str) -> list[str]:
    """Search terms: tokens without stopwords, stemmed. Numbers lose their thousands commas."""
    return [stem(t) for t in tokens(text) if t not in STOPWORDS]


def sentences(text: str) -> list[str]:
    """Split prose into sentences; every table row ('| a | b |') is its own sentence."""
    out: list[str] = []
    for block in text.split("\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("|"):
            out.append(block)
            continue
        out.extend(s.strip() for s in _SENTENCE_RE.split(block) if s.strip())
    return out


def normalise(text: str) -> str:
    """For keyword checks in the evaluation: lower case, '$' removed, single spaces."""
    return re.sub(r"\s+", " ", text.lower().replace("$", "")).strip()


def years_in(text: str) -> list[int]:
    return [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
