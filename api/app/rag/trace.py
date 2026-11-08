from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from app.llm.base import Completion
from app.models import TraceStep, Usage


class Trace:
    """Collects the steps of one run: what happened, how long it took, what it cost."""

    def __init__(self) -> None:
        self.steps: list[TraceStep] = []
        self.usage = Usage()
        self.model = ""
        self._start = time.perf_counter()

    @contextmanager
    def step(self, name: str, detail: str = "") -> Iterator[dict]:
        data: dict = {}
        started = time.perf_counter()
        try:
            yield data
        finally:
            ms = (time.perf_counter() - started) * 1000
            self.steps.append(TraceStep(name=name, detail=detail, data=data, ms=round(ms, 2)))

    def record(self, completion: Completion) -> Completion:
        self.usage.add(completion.usage)
        self.model = self.model or completion.model
        return completion

    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self._start) * 1000, 2)
