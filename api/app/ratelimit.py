"""Per-client rate limits (token buckets), kept in memory.

Every /api/ask costs model calls, so a client gets a bucket of N requests per minute that
refills continuously. In memory means per process: with several API instances each has its
own buckets, which still bounds abuse at N x instances. A shared store (Redis) is the next
step when that matters; the LLM Gateway's per-team budgets are the hard cap on spend.
"""

from __future__ import annotations

import math
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request


class RateLimiter:
    def __init__(self, per_minute: int, *, clock=time.monotonic, max_clients: int = 10_000):
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self._clock = clock
        self._max_clients = max_clients
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, updated)
        self._lock = threading.Lock()

    def check(self, key: str) -> float | None:
        """Take one token. Returns None if allowed, else seconds until the next token."""
        if self.capacity <= 0:
            return None  # disabled
        now = self._clock()
        with self._lock:
            tokens, updated = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - updated) * self.rate)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                self._evict(now)
                return None
            self._buckets[key] = (tokens, now)
            return (1 - tokens) / self.rate

    def _evict(self, now: float) -> None:
        if len(self._buckets) <= self._max_clients:
            return
        # Drop full buckets first: those clients have been idle for at least a minute.
        for key, (tokens, updated) in list(self._buckets.items()):
            if tokens + (now - updated) * self.rate >= self.capacity:
                del self._buckets[key]


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce(limiter: RateLimiter, request: Request) -> None:
    from fastapi import HTTPException

    wait = limiter.check(client_key(request))
    if wait is not None:
        raise HTTPException(
            429, "Too many requests; please wait a moment.",
            headers={"Retry-After": str(math.ceil(wait))},
        )
