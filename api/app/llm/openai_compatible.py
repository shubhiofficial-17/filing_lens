"""Client for any OpenAI-compatible `/chat/completions` endpoint.

In practice this points at the LLM Gateway (github.com/shubhiofficial-17/llm_gateway), which
already handles provider keys, fallbacks, caching and budgets. So this client stays small:
one retry for transient failures, and everything else is the gateway's job.
"""

from __future__ import annotations

import time

from app.llm.base import Completion, LlmError, Message
from app.models import Usage

# USD per million tokens (input, output). Unknown models are counted as zero cost.
PRICES = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
}


class _PermanentError(LlmError):
    """A 4xx answer: retrying the same request will not help."""


class OpenAICompatibleLlm:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: float = 60) -> None:
        import httpx

        self.name = model
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(timeout=timeout, headers=headers)
        self._httpx = httpx

    def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        max_tokens: int = 700,
        json_mode: bool = False,
    ) -> Completion:
        model = model or self._model
        body: dict = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                r = self._client.post(self._url, json=body)
                if r.status_code >= 500 or r.status_code == 429:
                    raise LlmError(f"model endpoint returned {r.status_code}")
                if r.status_code >= 400:
                    # A 4xx will not get better by retrying.
                    raise _PermanentError(
                        f"model endpoint returned {r.status_code}: {r.text[:200]}"
                    )
                data = r.json()
                text = data["choices"][0]["message"]["content"] or ""
                u = data.get("usage") or {}
                usage = Usage(
                    llm_calls=1,
                    prompt_tokens=int(u.get("prompt_tokens", 0)),
                    completion_tokens=int(u.get("completion_tokens", 0)),
                )
                usage.cost_usd = cost(model, usage.prompt_tokens, usage.completion_tokens)
                return Completion(text=text, model=data.get("model", model), usage=usage)
            except _PermanentError:
                raise
            except LlmError as e:
                last_error = e
            except (self._httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                last_error = e
            if attempt == 0:
                time.sleep(1.0)
        raise LlmError(f"model call failed: {last_error}")


def cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    return (prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000
