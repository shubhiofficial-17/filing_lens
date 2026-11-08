"""Builds the object graph once per process: store, ingestion and (later) retrieval."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import Settings
from app.ingest.service import Ingestor
from app.store.base import Store
from app.store.memory import InMemoryStore

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    store: Store
    ingestor: Ingestor
    persistent: bool

    def close(self) -> None:
        close = getattr(self.store, "close", None)
        if close:
            close()


def build_container(settings: Settings) -> Container:
    if settings.database_url:
        from app.store.postgres import PostgresStore

        store = PostgresStore(settings.database_url)
        store.open()
        persistent = True
    else:
        log.warning("FILINGLENS_DATABASE_URL is not set; using an in-memory store")
        store = InMemoryStore()
        persistent = False

    ingestor = Ingestor(store)
    if settings.seed_fixtures and store.count_filings() == 0:
        ingestor.ingest_fixtures()
    return Container(settings=settings, store=store, ingestor=ingestor, persistent=persistent)
