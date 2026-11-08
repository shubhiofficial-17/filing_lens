"""Structured outputs: ask for JSON, validate it, repair once, then fall back.

Models usually follow a JSON instruction, but "usually" is not a contract. Every structured
call goes through `complete_json`: extract the outermost JSON object (handles code fences
and chatter), validate it with a plain function, and on failure show the model its own
reply and the error once. If that also fails, the caller's fallback is used, so a bad
reply degrades the answer instead of crashing the request.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from app.llm.base import LlmClient, Message
from app.rag.trace import Trace


class InvalidOutput(ValueError):
    pass


def extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise InvalidOutput("no JSON object in the reply")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise InvalidOutput(f"invalid JSON: {e.msg}") from e
    if not isinstance(data, dict):
        raise InvalidOutput("the reply is not a JSON object")
    return data


def complete_json[T](
    llm: LlmClient,
    messages: list[Message],
    validate: Callable[[dict], T],
    fallback: T,
    trace: Trace,
    *,
    model: str | None = None,
) -> tuple[T, bool]:
    """Returns (value, ok). `ok` is False when the fallback was used."""
    reply = trace.record(llm.complete(messages, model=model, json_mode=True))
    try:
        return validate(extract_json(reply.text)), True
    except (InvalidOutput, KeyError, TypeError, ValueError) as first:
        repair = messages + [
            {"role": "assistant", "content": reply.text},
            {"role": "user", "content": f"That reply was invalid ({first}). Reply again with "
                                        "only the JSON object described above."},
        ]
        reply = trace.record(llm.complete(repair, model=model, json_mode=True))
        try:
            return validate(extract_json(reply.text)), True
        except (InvalidOutput, KeyError, TypeError, ValueError):
            return fallback, False
