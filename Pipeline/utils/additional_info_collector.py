"""Public entry points for resolving a company name to a ticker and building its financial snapshot."""
from typing import Optional

from Pipeline.utils.company_snapshot import CompanySnapshotBuilder
from Pipeline.utils.symbol_resolver import SymbolResolver

NON_LISTABLE_KEYWORDS = {
    "government", "ministry", "department", "agency",
    "ishares", "etf", "index", "fund",
    "partners", "llp", "ltd.", "limited", "incubator",
}

_symbol_resolver = SymbolResolver()
_snapshot_builder = CompanySnapshotBuilder()


def is_probably_non_listable(name: str) -> bool:
    tokens = _symbol_resolver.scorer.normalize_text(name).split()
    return any(keyword in tokens for keyword in NON_LISTABLE_KEYWORDS)


def get_company_symbol(company_name: str, region: Optional[str] = None,
                        finnhub_top_k: int = 3, force_refresh: bool = False) -> Optional[str]:
    """TickerResolver (and tests/test_server.py's mock) call this exact module path — see SymbolResolver.resolve."""
    return _symbol_resolver.resolve(company_name, region, finnhub_top_k, force_refresh)


def get_company_info(company_name: str, region: Optional[str] = None) -> dict:
    """report_generator.py calls this exact module path."""
    if is_probably_non_listable(company_name):
        return {"name": company_name, "symbol": None, "note": "non-listable or generic entity"}
    symbol = get_company_symbol(company_name, region=region)
    if not symbol:
        return {"name": company_name, "symbol": None, "note": "no reliable listing found"}
    snapshot = _snapshot_builder.build(symbol)
    snapshot["name"] = company_name
    return snapshot


if __name__ == "__main__":
    for company_name, region in [("Diamondback Energy", "US"), ("Tesco", "Europe"), ("ASML", "Europe"), ("HSBC Bank Malta", "Europe")]:
        try:
            print(get_company_info(company_name, region))
        except Exception as error:
            print(company_name, region, "ERR:", error)
