"""Registry of answering strategies, in the order they are compared."""

from __future__ import annotations

from app.rag.pipelines import NaiveRag, Pipeline

PIPELINES: dict[str, type[Pipeline]] = {
    NaiveRag.name: NaiveRag,
}
