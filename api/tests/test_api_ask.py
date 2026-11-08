import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(Settings(database_url=None))) as c:
        yield c


def test_strategies_are_listed(client):
    names = [s["name"] for s in client.get("/api/strategies").json()]
    assert "naive" in names


def test_ask_returns_a_cited_answer_with_a_trace(client):
    body = client.post(
        "/api/ask", json={"question": "What was Bluefin Health's net income in fiscal 2025?"}
    ).json()
    assert "58.9" in body["text"]
    assert body["citations"][0]["ticker"] == "BFHC"
    assert body["retrieved"][0]["text"]
    assert [s["name"] for s in body["trace"]][0] == "embed question"
    assert body["model"].startswith("demo")


def test_ask_applies_filters(client):
    body = client.post(
        "/api/ask", json={"question": "revenue", "tickers": ["sleh"], "years": [2024]}
    ).json()
    assert {(r["ticker"], r["fiscal_year"]) for r in body["retrieved"]} == {("SLEH", 2024)}


def test_ask_validates_input(client):
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 501}).status_code == 422
    r = client.post("/api/ask", json={"question": "What is revenue?", "strategy": "magic"})
    assert r.status_code == 422
