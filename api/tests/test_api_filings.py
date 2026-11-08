import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(Settings(database_url=None))) as c:
        yield c


def test_fixture_filings_are_seeded(client):
    filings = client.get("/api/filings").json()
    assert len(filings) == 9
    assert filings[0]["id"] == "BFHC-2023-10K"


def test_filing_lists_its_sections(client):
    body = client.get("/api/filings/NWRB-2024-10K").json()
    assert body["company"] == "Northwind Robotics, Inc."
    assert [s["item"] for s in body["sections"]] == ["1", "1A", "2", "3", "7", "8"]


def test_section_text(client):
    body = client.get("/api/sections/NWRB-2024-10K:1").json()
    assert "Helix Vision Ltd." in body["text"]


def test_unknown_ids_are_404(client):
    assert client.get("/api/filings/NOPE").status_code == 404
    assert client.get("/api/sections/NOPE:1").status_code == 404


def test_edgar_ingest_validates_the_request(client):
    assert client.post("/api/filings/ingest", json={"source": "edgar"}).status_code == 422
    assert client.post("/api/filings/ingest", json={"source": "ftp"}).status_code == 422
    assert client.post("/api/filings/ingest", json={"ticker": "A B"}).status_code == 422


def test_edgar_ingest_without_user_agent_explains_why(client):
    response = client.post("/api/filings/ingest", json={"ticker": "MSFT"})
    assert response.status_code == 502
    assert "User-Agent" in response.json()["detail"]
