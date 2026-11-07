"""Normalize and score raw ticker-search candidates against a query company name."""
import re
from typing import Any, Dict, List, Optional


class CandidateScorer:
    """
    Normalizes exchange/company names and scores a list of raw candidates
    (from Finnhub/Yahoo) against the query name and region, so
    `SymbolResolver` can pick the best one when neither source alone is
    confident.
    """

    JUNK_SYMBOL_PATTERN = re.compile(r'.*\b(WT|WS|W|U|UNIT|ADR|PRA|PRB|PRC|RIGHTS)\b', re.IGNORECASE)
    JUNK_NAME_PATTERN = re.compile(r'\b(warrant|units?|right|preferred|preference|etf|fund)\b', re.IGNORECASE)

    GLOBAL_EXCHANGE_PRIORITY: Dict[str, float] = {
        # US
        "NYSE": 1.0, "NASDAQ": 1.0, "NYSE ARCA": 0.85, "AMEX": 0.9, "NYSE MKT": 0.9,
        "OTC": 0.3, "PINK": 0.2,
        # UK/EU
        "LSE": 1.0, "AIM": 0.8, "XETRA": 1.0, "FWB": 0.95, "FRA": 0.9,
        "Euronext Paris": 1.0, "Euronext Amsterdam": 1.0, "Euronext Brussels": 0.95, "SIX": 0.95,
        # DE regional you mapped
        "SWB": 0.6,
        # AT / BR
        "VIE": 0.7, "B3": 0.8,
        # APAC
        "TSE": 1.0, "HKEX": 1.0, "ASX": 1.0, "SGX": 1.0,
        "NSE": 1.0, "BSE": 0.9, "KRX": 1.0,
    }

    REGION_EXCHANGE_PREFERENCES = {
        None: ["NYSE", "NASDAQ", "LSE", "XETRA", "Euronext Paris", "Euronext Amsterdam", "SIX"],
        "US": ["NYSE", "NASDAQ"],
        "Europe": ["LSE", "XETRA", "Euronext Paris", "Euronext Amsterdam", "Euronext Brussels", "SIX", "FRA", "FWB", "SWB", "VIE"],
        "UK": ["LSE"],
        "DE": ["XETRA", "FRA", "FWB", "SWB"],
        "FR": ["Euronext Paris"],
    }

    EXCHANGE_ALIASES: Dict[str, str] = {
        # US
        "NASDAQ": "NASDAQ", "NASDAQGS": "NASDAQ", "NASDAQGM": "NASDAQ", "NASDAQCM": "NASDAQ",
        "NYSE": "NYSE",
        "NYSE ARCA": "NYSE ARCA", "NYSEARCA": "NYSE ARCA",
        "NYSE AMERICAN": "AMEX", "AMEX": "AMEX", "NYSE MKT": "AMEX",
        "OTC": "OTC", "OTC MARKETS": "OTC", "OTC PINK": "PINK", "PINK SHEETS": "PINK", "PINK": "PINK",

        # UK/EU
        "LSE": "LSE", "LONDON": "LSE",
        "XETRA": "XETRA", "XETR": "XETRA", "XET": "XETRA",
        "FWB": "FWB", "FRANKFURT": "FRA", "FRA": "FRA",
        "HANOVER": "FWB",   # often grouped with FWB for scoring
        "STUTTGART": "SWB",
        "VIENNA": "VIE",
        "PARIS": "Euronext Paris", "EURONEXT PARIS": "Euronext Paris",
        "AMSTERDAM": "Euronext Amsterdam", "EURONEXT AMSTERDAM": "Euronext Amsterdam",
        "BRUSSELS": "Euronext Brussels", "EURONEXT BRUSSELS": "Euronext Brussels",
        "SIX": "SIX", "SIX SWISS EXCHANGE": "SIX",

        # APAC
        "HKEX": "HKEX", "HKSE": "HKEX",
        "TSE": "TSE", "JPX": "TSE", "TOKYO": "TSE",
        "ASX": "ASX",
        "SGX": "SGX",
        "NSE": "NSE", "NSEI": "NSE",
        "BSE": "BSE",
        "KRX": "KRX", "KSE": "KRX", "KOSPI": "KRX",

        # LATAM
        "SAO PAULO": "B3", "SÃO PAULO": "B3", "BOVESPA": "B3",
    }

    @staticmethod
    def normalize_text(text: str) -> str:
        return " ".join(re.sub(r"[^A-Za-z0-9&+\-\. ]+", " ", (text or "")).lower().split())

    @staticmethod
    def normalize_name(name: str) -> str:
        return ''.join(ch for ch in name.lower().strip() if ch.isalnum() or ch.isspace())

    def normalize_exchange(self, exchange_display: Optional[str]) -> str:
        """
        Map raw display exchange names (from Yahoo/Finnhub) to canonical keys
        used in GLOBAL_EXCHANGE_PRIORITY and REGION_EXCHANGE_PREFERENCES.
        Falls back to uppercase cleaned token if unknown.
        """
        cleaned = (exchange_display or "").strip().upper().replace(".", "")
        return self.EXCHANGE_ALIASES.get(cleaned, cleaned)

    def name_similarity_score(self, query_name: str, candidate_name: str) -> float:
        """Very light-weight token overlap (Jaccard)."""
        query_tokens = set(self.normalize_text(query_name).split())
        candidate_tokens = set(self.normalize_text(candidate_name).split())
        if not query_tokens or not candidate_tokens:
            return 0.0
        intersection = len(query_tokens & candidate_tokens)
        union = len(query_tokens | candidate_tokens)
        return intersection / union

    def score_candidate(
        self,
        candidate: Dict[str, Any],
        query_name: str,
        exchange_priority: Optional[Dict[str, float]] = None,
        allowed_exchanges: Optional[List[str]] = None,
    ) -> float:
        """
        Produce a composite score for a candidate using name similarity, exchange quality,
        and junk filtering. Higher is better.
        """
        exchange_raw = (candidate.get("exchange") or "").strip()
        exchange = self.normalize_exchange(exchange_raw)
        symbol = (candidate.get("symbol") or "").strip()
        name = candidate.get("name") or ""

        # Hard filter by allowed_exchanges if provided
        if allowed_exchanges and exchange and exchange not in allowed_exchanges:
            return float("-inf")

        score = float(candidate.get("match_score") or 0.0)

        # Lightly weight name similarity (0..1)
        score += 0.35 * self.name_similarity_score(query_name, name)

        # Exchange preference (global)
        exchange_preference = (exchange_priority or self.GLOBAL_EXCHANGE_PRIORITY).get(exchange, 0.4)
        score += 0.25 * exchange_preference

        # Penalize OTC/PINK
        if (exchange or "").upper() in {"OTC", "PINK"}:
            score -= 0.25

        # Penalize junk instruments
        if self.is_junk_symbol(symbol) or self.is_junk_name(name):
            score -= 0.6

        # Tiny bonus for primary symbols (no suffix)
        if "." not in symbol:
            score += 0.05

        return score

    def choose_best_candidate(
        self,
        candidates: List[Dict[str, Any]],
        query_name: str,
        exchange_priority: Optional[Dict[str, float]] = None,
        allowed_exchanges: Optional[List[str]] = None,
        min_accept_score: float = 0.3,
    ) -> Optional[Dict[str, Any]]:
        """Score all candidates and return the best one (or None if too weak)."""
        if not candidates:
            return None

        scored: List[tuple[float, Dict[str, Any]]] = []
        for candidate in candidates:
            scored.append((
                self.score_candidate(
                    candidate, query_name=query_name,
                    exchange_priority=exchange_priority, allowed_exchanges=allowed_exchanges,
                ),
                candidate,
            ))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        best_score, best_candidate = scored[0]
        if best_score < min_accept_score:
            return None
        return best_candidate

    def is_junk_symbol(self, symbol: str) -> bool:
        return bool(self.JUNK_SYMBOL_PATTERN.match(symbol or ""))

    def is_junk_name(self, name: str) -> bool:
        return bool(self.JUNK_NAME_PATTERN.search(name or ""))

    @staticmethod
    def symbol_root(symbol: Optional[str]) -> str:
        cleaned = (symbol or "").strip().upper()
        return cleaned.split(".", 1)[0] if "." in cleaned else cleaned

    def is_region_fit(self, exchange: Optional[str], region: Optional[str]) -> bool:
        normalized_exchange = self.normalize_exchange(exchange)
        allowed = self.REGION_EXCHANGE_PREFERENCES.get(region, self.REGION_EXCHANGE_PREFERENCES.get(None, []))
        return normalized_exchange in allowed if allowed else True
