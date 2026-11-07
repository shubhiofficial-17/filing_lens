import os

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import create_app

TEST_DATABASE_URL = os.environ.get("FILINGLENS_TEST_DATABASE_URL")


def test_health_is_ok_without_a_database():
    with TestClient(create_app(Settings(database_url=None))) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_ready_is_503_when_no_database_is_configured():
    with TestClient(create_app(Settings(database_url=None))) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "not configured"}


def test_openapi_is_served_under_api():
    with TestClient(create_app(Settings(database_url=None))) as client:
        response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert "/api/health/ready" in response.json()["paths"]


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="FILINGLENS_TEST_DATABASE_URL not set")
def test_ready_with_postgres_enables_pgvector():
    with TestClient(create_app(Settings(database_url=TEST_DATABASE_URL))) as client:
        response = client.get("/api/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["pgvector"]
