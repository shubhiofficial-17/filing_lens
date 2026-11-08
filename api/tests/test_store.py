import os

import pytest

from app.store.memory import InMemoryStore
from tests.store_contract import CHECKS

TEST_DATABASE_URL = os.environ.get("FILINGLENS_TEST_DATABASE_URL")


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.__name__)
def test_in_memory_store(check):
    check(InMemoryStore())


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="FILINGLENS_TEST_DATABASE_URL not set")
@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.__name__)
def test_postgres_store(check):
    from app.store.postgres import PostgresStore

    store = PostgresStore(TEST_DATABASE_URL)
    store.open()
    try:
        store.reset()
        check(store)
    finally:
        store.reset()
        store.close()
