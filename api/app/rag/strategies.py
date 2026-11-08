"""Registry of answering strategies, in the order they are compared."""

from __future__ import annotations

from app.rag.pipelines import HybridRag, NaiveRag, Pipeline

PIPELINES: dict[str, type[Pipeline]] = {
    NaiveRag.name: NaiveRag,
    HybridRag.name: HybridRag,
}
