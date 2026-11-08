"""Builds the object graph once per process: store, model, embedder, ingestion, strategies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.ingest.service import Ingestor
from app.llm.base import LlmClient
from app.llm.demo import DemoLlm
from app.rag.embeddings import Embedder, HashingEmbedder, OpenAICompatibleEmbedder
from app.rag.pipelines import RagContext
from app.store.base import Store
from app.store.memory import InMemoryStore

if TYPE_CHECKING:
    from app.config import Settings

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    store: Store
    ingestor: Ingestor
    rag: RagContext
    persistent: bool

    def close(self) -> None:
        close = getattr(self.store, "close", None)
        if close:
            close()


def build_llm(settings: Settings) -> LlmClient:
    if not settings.llm_base_url:
        log.warning("FILINGLENS_LLM_BASE_URL is not set; using the demo model (not an AI)")
        return DemoLlm()
    from app.llm.openai_compatible import OpenAICompatibleLlm

    return OpenAICompatibleLlm(settings.llm_base_url, settings.llm_model, settings.llm_api_key)


def build_embedder(settings: Settings) -> Embedder:
    base_url = settings.embeddings_base_url or ""
    if not base_url:
        return HashingEmbedder(settings.embedding_dim)
    return OpenAICompatibleEmbedder(
        base_url, settings.embeddings_model, settings.embedding_dim,
        api_key=settings.embeddings_api_key or settings.llm_api_key,
    )


def build_rag(settings: Settings, store: Store, llm: LlmClient) -> RagContext:
    embedder = build_embedder(settings)
    if settings.seed_fixtures and store.count_filings() == 0:
        Ingestor(store, embedder).ingest_fixtures()
    return RagContext(store=store, embedder=embedder, llm=llm, top_k=settings.top_k,
                      strong_model=settings.llm_strong_model or None)


def build_container(settings: Settings) -> Container:
    if settings.database_url:
        from app.store.postgres import PostgresStore

        store: Store = PostgresStore(settings.database_url, dim=settings.embedding_dim)
        store.open()  # type: ignore[attr-defined]
        persistent = True
    else:
        log.warning("FILINGLENS_DATABASE_URL is not set; using an in-memory store")
        store = InMemoryStore()
        persistent = False

    rag = build_rag(settings, store, build_llm(settings))
    return Container(
        settings=settings,
        store=store,
        ingestor=Ingestor(store, rag.embedder),
        rag=rag,
        persistent=persistent,
    )
