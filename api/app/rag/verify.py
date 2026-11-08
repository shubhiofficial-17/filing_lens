"""Is a claim supported by its evidence?

A cheap, deterministic check used everywhere a model's claim meets a source: the evaluation's
faithfulness score, the agent's citation verification and the fact-checker. It is lexical: a
claim is supported when most of its content words appear in the evidence and *every* number
in the claim appears there too. Numbers are where hallucinations hurt most in financial text,
so they are checked strictly.
"""

from __future__ import annotations

import re

from app.text import sentences, terms

_NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_MARKER_RE = re.compile(r"\s*\[\d+\]")

SUPPORT_THRESHOLD = 0.6


def strip_markers(text: str) -> str:
    return _MARKER_RE.sub("", text).strip()


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER_RE.findall(strip_markers(text))}


def support_score(claim: str, evidence: str) -> float:
    claim = strip_markers(claim)
    claim_terms = {t for t in terms(claim) if not t[0].isdigit()}
    evidence_terms = set(terms(evidence))
    missing_numbers = numbers(claim) - numbers(evidence)
    if missing_numbers:
        return 0.0
    if not claim_terms:
        return 1.0
    return len(claim_terms & evidence_terms) / len(claim_terms)


def is_supported(claim: str, evidence: str) -> bool:
    return support_score(claim, evidence) >= SUPPORT_THRESHOLD


def best_quote(claim: str, evidence: str) -> str:
    """The sentence of the evidence that best supports the claim (shown as the citation)."""
    candidates = sentences(evidence) or [evidence]
    return max(candidates, key=lambda s: support_score(claim, s) + 0.001 * len(s))
