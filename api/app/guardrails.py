"""Guardrails for untrusted text.

Filings are public documents anyone can write, and retrieved text goes straight into a
prompt. So retrieved text is treated like user input from a stranger:

1. Sanitise: sentences that look like instructions to an AI ("ignore all previous
   instructions", "note to automated readers", "you are now...") are removed from the
   excerpts before the model sees them, and every removal is recorded in the trace.
2. Fence: excerpts sit inside <excerpts> tags and the system prompt says they are data.
3. Verify: after the answer, every sentence must be supported by the excerpt it cites
   (see agents/verify.py), so an instruction that slips through still has to survive a
   citation check.

No single layer is enough; together they make an injection have to beat all three.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from app.models import Hit
from app.text import sentences

INJECTION_PATTERNS = [
    r"\bignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) "
    r"(?:instructions|prompts?|rules)",
    r"\bdisregard (?:all |any )?(?:the )?(?:previous|prior|above|earlier|your)\b",
    r"\bnote to (?:automated|ai|llm|machine) (?:readers|systems|assistants)",
    r"\byou are now\b",
    r"\b(?:system|developer) prompt\b",
    r"\bact as (?:an?|the) \w+",
    r"\bdo not (?:tell|reveal|mention) (?:the user|anyone)",
    r"\b(?:respond|reply|answer) only with\b",
    r"^\s*(?:assistant|system)\s*:",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.I | re.M)


@dataclass
class Flag:
    chunk_id: str
    sentence: str


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text))


def sanitise_hits(hits: list[Hit]) -> tuple[list[Hit], list[Flag]]:
    """Remove instruction-like sentences from retrieved chunks."""
    flags: list[Flag] = []
    out: list[Hit] = []
    for h in hits:
        if not looks_like_injection(h.chunk.text):
            out.append(h)
            continue
        kept = []
        for block in h.chunk.text.split("\n\n"):
            clean = []
            for s in sentences(block):
                if looks_like_injection(s):
                    flags.append(Flag(h.chunk.id, s))
                else:
                    clean.append(s)
            if clean:
                kept.append(" ".join(clean))
        text = "\n\n".join(kept) or "[removed: instructions found in the source text]"
        out.append(Hit(replace(h.chunk, text=text), h.score, h.source))
    return out, flags
