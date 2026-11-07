"""Fetch raw ticker candidates from Finnhub and Yahoo's company search endpoints."""
from typing import Any, Dict, List

import requests

from Pipeline.config import FINNHUB_API_KEY


class SymbolFetcher:
    """Each method returns a list of raw candidate dicts: symbol, name, exchange, region, currency, match_score, type."""

    def fetch_finnhub(self, company_name: str) -> List[Dict[str, Any]]:
        if not FINNHUB_API_KEY:
            return []
        url = "https://finnhub.io/api/v1/search"
        query_parameters = {"q": company_name, "token": FINNHUB_API_KEY}
        response = requests.get(url, params=query_parameters, timeout=10)
        if response.status_code in (402, 403, 429):    # payment/quota/rate-limit
            return []
        response.raise_for_status()
        data = response.json() or {}
        results = []
        for item in data.get("result", []) or []:
            # Filter to equities only
            if (item.get("type") or "").upper() not in {"EQUITY", "COMMON STOCK", "STOCK"}:
                continue
            results.append({
                "symbol": item.get("symbol"),
                "name": item.get("description"),
                "exchange": item.get("exchange"),     # e.g., NASDAQ
                "region": None,                       # not provided here
                "currency": None,
                "match_score": 0.0,                   # no score from API; the scorer adds name similarity
                "type": item.get("type"),
            })
        return results

    def fetch_yahoo(self, company_name: str) -> List[Dict[str, Any]]:
        url = "https://query1.finance.yahoo.com/v1/finance/search"
        query_parameters = {"q": company_name, "quotesCount": 10, "newsCount": 0}
        response = requests.get(url, params=query_parameters, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code in (404, 422, 429, 503):
            return []
        response.raise_for_status()
        data = response.json() or {}
        results: List[Dict[str, Any]] = []
        for quote in data.get("quotes", []) or []:
            quote_type = (quote.get("quoteType") or "").upper()
            if quote_type != "EQUITY":
                continue
            results.append({
                "symbol": quote.get("symbol"),
                "name": quote.get("longname") or quote.get("shortname") or "",
                "exchange": quote.get("exchDisp"),             # e.g., NasdaqGS
                "region": None,
                "currency": quote.get("currency"),
                "match_score": float(quote.get("score") or 0.0),  # present on some responses
                "type": quote_type,
            })
        return results

    def fetch_any(self, company_name: str) -> list[dict]:
        """Finnhub first, Yahoo as a fallback if Finnhub raises or returns nothing."""
        try:
            hits = self.fetch_finnhub(company_name)
            if hits:
                return hits
        except Exception:
            pass
        try:
            return self.fetch_yahoo(company_name)
        except Exception:
            return []
