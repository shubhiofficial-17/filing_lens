"""Citation verification: the last gate before an answer leaves the agent.

Every sentence must be supported by the excerpt it cites. A sentence whose citation is
wrong but whose claim another excerpt supports is re-cited. A sentence nothing supports is
removed. If nothing survives, the answer becomes the standard refusal. This catches
hallucinated numbers, mixed-up years and instructions that slipped past sanitisation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import Hit
from app.rag.prompts import NO_ANSWER
from app.rag.verify import strip_markers, support_score
from app.text import sentences

_MARKER_RE = re.compile(r"\[(\d+)\]")
THRESHOLD = 0.6


@dataclass
class Check:
    sentence: str
    status: str  # "kept" | "re-cited" | "removed"
    cited: list[int]


def verify_answer(text: str, hits: list[Hit]) -> tuple[str, list[Check]]:
    if text.strip() == NO_ANSWER:
        return text, []
    evidence = {n: h.chunk.evidence() for n, h in enumerate(hits, 1)}
    kept: list[str] = []
    checks: list[Check] = []
    for sentence in sentences(text):
        claim = strip_markers(sentence)
        if not claim or claim == NO_ANSWER:
            continue
        cited = [int(m) for m in _MARKER_RE.findall(sentence) if int(m) in evidence]
        joined = " ".join(evidence[n] for n in cited)
        if claim in (c.sentence for c in checks if c.status != "removed"):
            continue  # the same claim twice
        if cited and support_score(claim, joined) >= THRESHOLD:
            kept.append(sentence)
            checks.append(Check(claim, "kept", cited))
            continue
        best = max(evidence, key=lambda n: support_score(claim, evidence[n]), default=None)
        if best is not None and support_score(claim, evidence[best]) >= THRESHOLD:
            kept.append(f"{claim.rstrip('.')} [{best}].")
            checks.append(Check(claim, "re-cited", [best]))
        else:
            checks.append(Check(claim, "removed", cited))
    return (" ".join(kept) if kept else NO_ANSWER), checks
