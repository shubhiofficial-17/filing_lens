"""Embedders.

- `HashingEmbedder`: deterministic, offline, no model. Feature hashing of stemmed words and
  word pairs into a fixed number of dimensions. It is lexical, not semantic, and is used for
  tests, CI and the demo mode. It keeps the whole pipeline runnable without an API key.
- `OpenAICompatibleEmbedder`: any `/embeddings` endpoint (the LLM Gateway, OpenAI, Ollama...).
"""

from __future__ import annotations

import math
import zlib
from typing import Protocol

from app.text import terms


class Embedder(Protocol):
    dim: int
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        words = terms(text)
        features = words + [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
        counts: dict[str, int] = {}
        for f in features:
            counts[f] = counts.get(f, 0) + 1
        for feature, count in counts.items():
            h = zlib.crc32(feature.encode())
            sign = 1.0 if h & 1 else -1.0
            vec[(h >> 1) % self.dim] += sign * (1.0 + math.log(count))
        return normalise(vec)


class EmbeddingError(Exception):
    pass


class OpenAICompatibleEmbedder:
    def __init__(self, base_url: str, model: str, dim: int, api_key: str = "", batch: int = 64):
        import httpx

        self.dim = dim
        self.name = model
        self._url = base_url.rstrip("/") + "/embeddings"
        self._model = model
        self._batch = batch
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(timeout=60, headers=headers)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch):
            batch = texts[i : i + self._batch]
            try:
                r = self._client.post(
                    self._url,
                    json={"model": self._model, "input": batch, "dimensions": self.dim},
                )
                r.raise_for_status()
                data = sorted(r.json()["data"], key=lambda d: d["index"])
            except Exception as e:  # network, HTTP or shape errors
                raise EmbeddingError(f"embedding request failed: {e}") from e
            for d in data:
                vec = d["embedding"]
                if len(vec) != self.dim:
                    raise EmbeddingError(
                        f"model returned {len(vec)} dimensions, FILINGLENS_EMBEDDING_DIM is "
                        f"{self.dim}"
                    )
                out.append(normalise(vec))
        return out


def normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def cosine(a: list[float], b: list[float]) -> float:
    """Both vectors are already unit length, so cosine similarity is the dot product."""
    return sum(x * y for x, y in zip(a, b, strict=False))
