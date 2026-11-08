from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.models import Usage

Message = dict[str, str]  # {"role": "system" | "user" | "assistant", "content": "..."}


class LlmError(Exception):
    """The model could not be reached or returned something unusable."""


@dataclass
class Completion:
    text: str
    model: str
    usage: Usage = field(default_factory=Usage)


class LlmClient(Protocol):
    name: str

    def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int = 700,
        json_mode: bool = False,
    ) -> Completion: ...


def estimate_tokens(text: str) -> int:
    """About four characters per token for English text; good enough for budgets."""
    return max(1, len(text) // 4)
