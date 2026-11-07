"""Resolve a company name to a stock ticker."""
from typing import Any, Dict, List, Optional

import requests

from Pipeline.utils.candidate_scorer import CandidateScorer
from Pipeline.utils.symbol_cache import SymbolCache
from Pipeline.utils.symbol_fetcher import SymbolFetcher


class SymbolResolver:
    """
    Resolves one company name to one ticker by trying a short chain of
    strategies in order — Yahoo's top hit, a Finnhub cross-check against
    it, then a scored pick over both sources combined — stopping at the
    first strategy that produces a confident symbol. Each strategy method
    returns `(symbol, satisfied)`, the same shape `PipelineModule.run()`
    and `Pipeline.main.execute_pipeline` use to decide whether to move on,
    kept here as a small synchronous chain rather than the full pipeline
    machinery, since this runs once per company, not once per pipeline run.
    """

    def __init__(self, cache: Optional[SymbolCache] = None, scorer: Optional[CandidateScorer] = None,
                 fetcher: Optional[SymbolFetcher] = None):
        self.cache = cache if cache is not None else SymbolCache()
        self.scorer = scorer if scorer is not None else CandidateScorer()
        self.fetcher = fetcher if fetcher is not None else SymbolFetcher()

    def resolve(self, company_name: str, region: Optional[str] = None,
                finnhub_top_k: int = 3, force_refresh: bool = False) -> Optional[str]:
        """Yahoo-first, Finnhub-verify, then last-resort scorer. Caches by normalized company name (+ region)."""
        cache_key = self.scorer.normalize_name(company_name) + (f"|{region}" if region else "")
        if not force_refresh and self.cache.has(cache_key):
            return self.cache.get(cache_key)

        yahoo_candidates = self.fetcher.fetch_yahoo(company_name)
        best_yahoo = yahoo_candidates[0] if yahoo_candidates else None
        finnhub_candidates: List[Dict[str, Any]] = []

        symbol, satisfied = self._from_yahoo_top_hit(company_name, region, yahoo_candidates, best_yahoo)
        if not satisfied:
            try:
                finnhub_candidates = self.fetcher.fetch_finnhub(company_name)[:finnhub_top_k]
            except requests.RequestException:
                finnhub_candidates = []
            symbol, satisfied = self._from_finnhub_cross_check(region, best_yahoo, finnhub_candidates)
        if not satisfied:
            symbol, satisfied = self._from_scored_fallback(company_name, region, yahoo_candidates, finnhub_candidates)

        resolved_symbol = symbol if satisfied else None
        self.cache.set(cache_key, resolved_symbol)
        return resolved_symbol

    def _from_yahoo_top_hit(self, company_name, region, yahoo_candidates, best_yahoo) -> tuple[Optional[str], bool]:
        if not best_yahoo:
            return None, False
        scores = [float(candidate.get("match_score") or 0.0) for candidate in yahoo_candidates]
        top_score = max(scores) if scores else 0.0
        best_score = float(best_yahoo.get("match_score") or 0.0)
        name_similarity = self.scorer.name_similarity_score(company_name, best_yahoo.get("name") or "")
        acceptance_bar = top_score * 0.98 if top_score else 0.0
        is_confident = (top_score > 0 and best_score >= acceptance_bar) or name_similarity >= 0.60
        if is_confident and self.scorer.is_region_fit(best_yahoo.get("exchange"), region):
            return best_yahoo.get("symbol"), True
        return None, False

    def _from_finnhub_cross_check(self, region, best_yahoo, finnhub_candidates) -> tuple[Optional[str], bool]:
        if not best_yahoo:
            return None, False
        yahoo_root = self.scorer.symbol_root(best_yahoo.get("symbol"))
        yahoo_name = best_yahoo.get("name") or ""
        for finnhub_candidate in finnhub_candidates:
            finnhub_root = self.scorer.symbol_root(finnhub_candidate.get("symbol"))
            same_company = (
                (yahoo_root and finnhub_root and yahoo_root == finnhub_root)
                or self.scorer.name_similarity_score(yahoo_name, finnhub_candidate.get("name") or "") >= 0.70
            )
            if not same_company:
                continue
            yahoo_region_fit = self.scorer.is_region_fit(best_yahoo.get("exchange"), region)
            finnhub_region_fit = self.scorer.is_region_fit(finnhub_candidate.get("exchange"), region)
            symbol = (
                (finnhub_candidate.get("symbol") if (finnhub_region_fit and not yahoo_region_fit) else best_yahoo.get("symbol"))
                if (yahoo_region_fit or finnhub_region_fit) else best_yahoo.get("symbol")
            )
            return symbol, True
        return None, False

    def _from_scored_fallback(self, company_name, region, yahoo_candidates, finnhub_candidates) -> tuple[Optional[str], bool]:
        combined: List[Dict[str, Any]] = []
        for candidate in (yahoo_candidates or []):
            normalized_candidate = dict(candidate)
            normalized_candidate["exchange"] = self.scorer.normalize_exchange(normalized_candidate.get("exchange"))
            combined.append(normalized_candidate)
        for candidate in (finnhub_candidates or []):
            normalized_candidate = dict(candidate)
            normalized_candidate["exchange"] = self.scorer.normalize_exchange(normalized_candidate.get("exchange"))
            combined.append(normalized_candidate)

        seen_roots = set()
        unique: List[Dict[str, Any]] = []
        for candidate in combined:
            root = self.scorer.symbol_root(candidate.get("symbol"))
            if root and root not in seen_roots:
                unique.append(candidate)
                seen_roots.add(root)

        allowed_exchanges = self.scorer.REGION_EXCHANGE_PREFERENCES.get(region)
        best_candidate = self.scorer.choose_best_candidate(unique, query_name=company_name, allowed_exchanges=allowed_exchanges)
        if best_candidate is None:
            return None, False
        return best_candidate.get("symbol"), True
