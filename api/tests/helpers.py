"""Shared test setup: the fixture corpus in an in-memory store, built once per process."""

from functools import lru_cache

from app.ingest.service import Ingestor
from app.llm.demo import DemoLlm
from app.rag.embeddings import HashingEmbedder
from app.rag.pipelines import RagContext
from app.store.memory import InMemoryStore


@lru_cache
def fixture_store() -> InMemoryStore:
    store = InMemoryStore()
    Ingestor(store, HashingEmbedder()).ingest_fixtures()
    return store


def rag(llm=None) -> RagContext:
    return RagContext(store=fixture_store(), embedder=HashingEmbedder(), llm=llm or DemoLlm())


class ScriptedLlm:
    """Returns canned replies in order and records every request."""

    name = "scripted"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.requests: list[list[dict]] = []

    def complete(self, messages, *, model=None, max_tokens=700, json_mode=False):
        from app.llm.base import Completion
        from app.models import Usage

        self.requests.append(messages)
        text = self.replies.pop(0) if self.replies else ""
        return Completion(text=text, model=model or "scripted", usage=Usage(llm_calls=1))
