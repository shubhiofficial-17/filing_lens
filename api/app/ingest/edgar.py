"""SEC EDGAR client: ticker -> CIK -> recent 10-K filings -> primary HTML document.

SEC's fair-access rules: identify yourself with a User-Agent that includes contact details,
and stay under 10 requests per second. Both are enforced here.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models import Filing

if TYPE_CHECKING:
    import httpx

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"


class EdgarError(Exception):
    pass


@dataclass(frozen=True)
class EdgarFiling:
    filing: Filing
    document_url: str


class EdgarClient:
    def __init__(
        self,
        user_agent: str,
        *,
        client: httpx.Client | None = None,
        min_interval: float = 0.12,
    ) -> None:
        if not user_agent or "@" not in user_agent:
            raise EdgarError(
                "SEC requires a User-Agent with contact details, for example "
                "'FilingLens you@example.com'. Set FILINGLENS_EDGAR_USER_AGENT."
            )
        import httpx

        self._client = client or httpx.Client(timeout=30, follow_redirects=True)
        self._headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        self._min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()
        self._tickers: dict[str, tuple[str, str]] | None = None

    def _get(self, url: str) -> httpx.Response:
        with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        response = self._client.get(url, headers=self._headers)
        if response.status_code == 404:
            raise EdgarError(f"not found: {url}")
        if response.status_code >= 400:
            raise EdgarError(f"EDGAR returned {response.status_code} for {url}")
        return response

    def lookup(self, ticker: str) -> tuple[str, str]:
        """Ticker -> (10-digit CIK, company name)."""
        if self._tickers is None:
            data = self._get(TICKERS_URL).json()
            self._tickers = {
                row["ticker"].upper(): (str(row["cik_str"]).zfill(10), row["title"])
                for row in data.values()
            }
        found = self._tickers.get(ticker.strip().upper())
        if not found:
            raise EdgarError(f"unknown ticker: {ticker}")
        return found

    def annual_reports(self, ticker: str, limit: int = 3) -> list[EdgarFiling]:
        """The most recent 10-K filings (amendments excluded), newest first."""
        ticker = ticker.strip().upper()
        cik, name = self.lookup(ticker)
        recent = self._get(SUBMISSIONS_URL.format(cik=cik)).json()["filings"]["recent"]
        out: list[EdgarFiling] = []
        for i, form in enumerate(recent["form"]):
            if form != "10-K":
                continue
            accession = recent["accessionNumber"][i]
            report_date = recent["reportDate"][i] or recent["filingDate"][i]
            url = ARCHIVE_URL.format(
                cik=int(cik), accession=accession.replace("-", ""),
                document=recent["primaryDocument"][i],
            )
            out.append(
                EdgarFiling(
                    filing=Filing(
                        id=accession,
                        ticker=ticker,
                        company=name,
                        cik=cik,
                        fiscal_year=int(report_date[:4]),
                        filed_on=recent["filingDate"][i],
                        source_url=url,
                    ),
                    document_url=url,
                )
            )
            if len(out) >= limit:
                break
        return out

    def document(self, url: str) -> str:
        return self._get(url).text
