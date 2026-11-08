"""HTTP endpoints. Handlers are plain `def`s: FastAPI runs them in a thread pool, which suits
the synchronous store and model clients."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.container import Container
from app.ingest.edgar import EdgarClient, EdgarError
from app.ingest.service import IngestError

router = APIRouter(prefix="/api")


def _container(request: Request) -> Container:
    return request.app.state.container


@router.get("/filings")
def list_filings(request: Request) -> list[dict]:
    return [asdict(f) for f in _container(request).store.list_filings()]


@router.get("/filings/{filing_id}")
def get_filing(filing_id: str, request: Request) -> dict:
    store = _container(request).store
    filing = store.get_filing(filing_id)
    if filing is None:
        raise HTTPException(404, "filing not found")
    sections = [
        {"id": s.id, "item": s.item, "title": s.title, "words": len(s.text.split())}
        for s in store.list_sections(filing_id)
    ]
    return {**asdict(filing), "sections": sections}


@router.get("/sections/{section_id}")
def get_section(section_id: str, request: Request) -> dict:
    section = _container(request).store.get_section(section_id)
    if section is None:
        raise HTTPException(404, "section not found")
    return asdict(section)


class IngestRequest(BaseModel):
    source: str = Field("edgar", pattern="^(edgar|fixtures)$")
    ticker: str | None = Field(None, min_length=1, max_length=10, pattern=r"^[A-Za-z.\-]+$")
    limit: int = Field(3, ge=1, le=5)


@router.post("/filings/ingest")
def ingest(body: IngestRequest, request: Request) -> dict:
    container = _container(request)
    try:
        if body.source == "fixtures":
            results = container.ingestor.ingest_fixtures()
        else:
            if not body.ticker:
                raise HTTPException(422, "ticker is required for EDGAR ingestion")
            client = EdgarClient(container.settings.edgar_user_agent)
            results = container.ingestor.ingest_edgar(client, body.ticker, body.limit)
    except EdgarError as e:
        raise HTTPException(502, str(e)) from e
    except IngestError as e:
        raise HTTPException(422, str(e)) from e
    return {"ingested": [{"id": r.filing.id, "sections": r.sections} for r in results]}
