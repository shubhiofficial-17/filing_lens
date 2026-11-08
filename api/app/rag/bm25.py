"""A small BM25 index for the in-memory store (Postgres uses its own full-text search)."""

from __future__ import annotations

import math
from collections import Counter

from app.text import terms


class Bm25Index:
    def __init__(self, k1: float = 1.2, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._tf: dict[str, Counter[str]] = {}
        self._len: dict[str, int] = {}
        self._df: Counter[str] = Counter()

    def add(self, doc_id: str, text: str) -> None:
        self.remove(doc_id)
        tf = Counter(terms(text))
        self._tf[doc_id] = tf
        self._len[doc_id] = sum(tf.values())
        self._df.update(tf.keys())

    def remove(self, doc_id: str) -> None:
        tf = self._tf.pop(doc_id, None)
        self._len.pop(doc_id, None)
        if tf:
            self._df.subtract(tf.keys())

    def scores(self, query: str, allowed: set[str] | None = None) -> dict[str, float]:
        q = set(terms(query))
        n = len(self._tf)
        if not q or not n:
            return {}
        avg = sum(self._len.values()) / n
        idf = {t: math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5)) for t in q}
        out: dict[str, float] = {}
        for doc_id, tf in self._tf.items():
            if allowed is not None and doc_id not in allowed:
                continue
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    norm = f + self.k1 * (1 - self.b + self.b * self._len[doc_id] / avg)
                    s += idf[t] * f * (self.k1 + 1) / norm
            if s > 0:
                out[doc_id] = s
        return out
