from config import ALPHA_VANTAGE_API_KEY, FINNHUB_API_KEY
import os
import platform
import socket
import requests
from pathlib import Path
import json
import re
from typing import Dict, Optional, List, Any
import time
import pandas as pd

# --- Enable yfinance curl_cffi before importing yfinance ---
if "YF_USE_CURL_CFFI" not in os.environ:
    os.environ["YF_USE_CURL_CFFI"] = "1"
# os.environ["YF_DEBUG"] = "1"  # optional

import yfinance as yf  # must be imported after env var above

_session = None
MODULE_DIR = Path(__file__).resolve().parent
CACHE_PATH = MODULE_DIR / "symbol_cache.json"

JUNK_SYMBOL_PAT = re.compile(r'.*\b(WT|WS|W|U|UNIT|ADR|PRA|PRB|PRC|RIGHTS)\b', re.IGNORECASE)
JUNK_NAME_PAT = re.compile(r'\b(warrant|units?|right|preferred|preference|etf|fund)\b', re.IGNORECASE)

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
    "NSE": 1.0, "BSE": 0.9, "KRX": 1.0
}

REGION_EXCHANGE_PREFS = {
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
    "HANOVER": "FWB",
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

NON_LISTABLE_KEYWORDS = {
    "government","ministry","department","agency",
    "ishares","etf","index","fund",
    "partners","llp","ltd.","limited","incubator"
}

symbol_cache = {}
try:
    if CACHE_PATH.exists():
        symbol_cache = json.loads(CACHE_PATH.read_text())
except Exception:
    symbol_cache = {}


# ---------------- Runtime diagnostics ----------------

def get_public_ip_candidates(timeout: float = 5.0) -> List[str]:
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://ipinfo.io/ip",
    ]
    ips: List[str] = []
    for url in services:
        try:
            r = requests.get(url, timeout=timeout)
            if r.ok:
                ips.append(r.text.strip())
        except Exception:
            pass
    return ips

def get_local_ip_addresses() -> List[str]:
    ips = set()
    try:
        hostname = socket.gethostname()
        for fam in (socket.AF_INET, socket.AF_INET6):
            try:
                for info in socket.getaddrinfo(hostname, None, family=fam):
                    ip = info[4][0]
                    if not ip.startswith("127.") and ip != "::1":
                        ips.add(ip)
            except Exception:
                continue
    except Exception:
        pass
    return sorted(ips)

def print_system_info():
    print("=== SYSTEM / RUNTIME INFO ===")
    print(f"python_version        : {platform.python_version()}")
    print(f"platform              : {platform.platform()}")
    print(f"system                : {platform.system()} {platform.release()}")
    print(f"machine               : {platform.machine()}")
    try:
        import yfinance as _yf
        print(f"yfinance_version      : {_yf.__version__}")
    except Exception:
        print("yfinance_version      : <unavailable>")
    print(f"requests_version      : {requests.__version__}")
    print(f"pid                   : {os.getpid()}")
    print(f"cwd                   : {os.getcwd()}")
    print(f"hostname              : {socket.gethostname()}")
    print(f"GITHUB_ACTIONS        : {os.environ.get('GITHUB_ACTIONS')}")
    print(f"RUNNER_NAME           : {os.environ.get('RUNNER_NAME')}")
    print(f"RUNNER_OS             : {os.environ.get('RUNNER_OS')}")
    print(f"RUNNER_ARCH           : {os.environ.get('RUNNER_ARCH')}")
    print(f"http_proxy            : {os.environ.get('http_proxy')}")
    print(f"https_proxy           : {os.environ.get('https_proxy')}")
    print(f"no_proxy              : {os.environ.get('no_proxy')}")
    local_ips = get_local_ip_addresses()
    print(f"local_ips             : {local_ips}")
    public_ips = get_public_ip_candidates()
    print(f"public_ips            : {public_ips if public_ips else '<unresolved>'}")
    print("==============================\n")


# ---------------- Sessions & utilities ----------------

def _get_session():
    """
    Shared requests session for non-yfinance calls (Finnhub, Yahoo search).
    Do NOT pass this into yfinance.Ticker.
    """
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        })
        _session = s
    return _session

def normalize_text(s: str) -> str:
    return " ".join(re.sub(r"[^A-Za-z0-9&+\-\. ]+", " ", (s or "")).lower().split())

def normalize_exchange(exchange_disp: Optional[str]) -> str:
    disp = (exchange_disp or "").strip().upper().replace(".", "")
    return EXCHANGE_ALIASES.get(disp, disp)

def name_similarity_score(query_name: str, candidate_name: str) -> float:
    q = set(normalize_text(query_name).split())
    c = set(normalize_text(candidate_name).split())
    if not q or not c:
        return 0.0
    inter = len(q & c)
    union = len(q | c)
    return inter / union

def with_backoff(func, *args, max_retries: int = 3, base_sleep: float = 1.0, **kwargs):
    for attempt in range(1, max_retries + 1):
        try:
            return func(*args, **kwargs)
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status == 429:
                print(f"[WARN] 429 Too Many Requests on attempt {attempt}/{max_retries}. Backing off...")
                time.sleep(base_sleep * attempt)
                continue
            raise
        except Exception as e:
            if attempt < max_retries:
                print(f"[WARN] transient error ({e}) on attempt {attempt}/{max_retries}. Retrying...")
                time.sleep(base_sleep * attempt)
                continue
            raise


# ---------------- Candidate scoring ----------------

def score_candidate_global(
    candidate: Dict[str, Any],
    query_name: str,
    exchange_priority: Optional[Dict[str, float]] = None,
    allowed_exchanges: Optional[List[str]] = None,
) -> float:
    ex_raw = (candidate.get("exchange") or "").strip()
    ex = normalize_exchange(ex_raw)
    sym = (candidate.get("symbol") or "").strip()
    name = candidate.get("name") or ""

    if allowed_exchanges and ex and ex not in allowed_exchanges:
        return float("-inf")

    base = float(candidate.get("match_score") or 0.0)

    base += 0.35 * name_similarity_score(query_name, name)

    ex_pref = (exchange_priority or GLOBAL_EXCHANGE_PRIORITY).get(ex, 0.4)
    base += 0.25 * ex_pref

    if (ex or "").upper() in {"OTC", "PINK"}:
        base -= 0.25

    if is_junk_symbol(sym) or is_junk_name(name):
        base -= 0.6

    if "." not in sym:
        base += 0.05

    return base

def choose_best_symbol_global(
    candidates: List[Dict[str, Any]],
    query_name: str,
    exchange_priority: Optional[Dict[str, float]] = None,
    allowed_exchanges: Optional[List[str]] = None,
    min_accept_score: float = 0.3
) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None

    scored: List[tuple[float, Dict[str, Any]]] = []
    for c in candidates:
        s = score_candidate_global(
            c,
            query_name=query_name,
            exchange_priority=exchange_priority,
            allowed_exchanges=allowed_exchanges,
        )
        scored.append((s, c))

    scored.sort(key=lambda t: t[0], reverse=True)
    best_score, best_cand = scored[0]
    if best_score < min_accept_score:
        return None
    return best_cand


# ---------------- Cache helpers ----------------

def save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))

def normalize_name(name: str) -> str:
    return ''.join(ch for ch in name.lower().strip() if ch.isalnum() or ch.isspace())


# ---------------- Lookups ----------------

def lookup_symbol_company(company_name: str) -> List[Dict[str, Any]]:
    try:
        hits = lookup_symbol_company_finnhub(company_name)
        if hits:
            return hits
    except Exception:
        pass
    try:
        hits = lookup_symbol_company_yahoo(company_name)
        return hits
    except Exception:
        return []

def lookup_symbol_company_finnhub(company_name: str) -> List[Dict[str, Any]]:
    url = "https://finnhub.io/api/v1/search"
    params = {"q": company_name, "token": FINNHUB_API_KEY}
    r = _get_session().get(url, params=params, timeout=10)
    if r.status_code in (402, 403, 429):
        return []
    r.raise_for_status()
    data = r.json() or {}
    results = []
    for item in data.get("result", []) or []:
        if (item.get("type") or "").upper() not in {"EQUITY", "COMMON STOCK", "STOCK"}:
            continue
        results.append({
            "symbol": item.get("symbol"),
            "name": item.get("description"),
            "exchange": item.get("exchange"),
            "region": None,
            "currency": None,
            "match_score": 0.0,
            "type": item.get("type"),
        })
    return results

def lookup_symbol_company_yahoo(company_name: str) -> List[Dict[str, Any]]:
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": company_name, "quotesCount": 10, "newsCount": 0}
    r = _get_session().get(url, params=params, timeout=10)
    if r.status_code in (404, 422, 429, 503):
        print(f"Error: {r.status_code}")
        return []
    r.raise_for_status()
    data = r.json() or {}
    results: List[Dict[str, Any]] = []
    for q in data.get("quotes", []) or []:
        quote_type = (q.get("quoteType") or "").upper()
        if quote_type != "EQUITY":
            continue
        results.append({
            "symbol": q.get("symbol"),
            "name": q.get("longname") or q.get("shortname") or "",
            "exchange": q.get("exchDisp"),
            "region": None,
            "currency": q.get("currency"),
            "match_score": float(q.get("score") or 0.0),
            "type": quote_type,
        })
    return results


# ---------------- Filters & buckets ----------------

def is_junk_symbol(symbol: str) -> bool:
    return bool(JUNK_SYMBOL_PAT.match(symbol or ""))

def is_junk_name(name: str) -> bool:
    return bool(JUNK_NAME_PAT.search(name or ""))

def cap_bucket(market_capitalization: Optional[int]) -> Optional[str]:
    if market_capitalization is None:
        return None
    if market_capitalization < 2_000_000_000:
        return "small_cap"
    if market_capitalization < 10_000_000_000:
        return "mid_cap"
    return "large_cap"


# ---------------- yfinance snapshot ----------------

def safe_get_fast_info(ticker: yf.Ticker, field_name: str):
    try:
        fast_info_object = getattr(ticker, "fast_info", None) or {}
        return fast_info_object.get(field_name)
    except Exception:
        return None

def safe_get_info(ticker: yf.Ticker, field_name: str) -> Any:
    try:
        info_dict = ticker.info or {}
        return info_dict.get(field_name)
    except requests.HTTPError as e:
        if getattr(e.response, "status_code", None) == 429:
            print(f"[WARN] 429 when accessing .info for {ticker.ticker}")
        raise
    except Exception:
        return None

def latest_financial_row(financials_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    try:
        if financials_df is None or financials_df.empty:
            return {}
        latest_period = financials_df.columns[0]
        latest_period_series = financials_df[latest_period]
        return {
            str(line_item): (
                None if pd.isna(latest_period_series[line_item]) 
                else latest_period_series[line_item]
            )
            for line_item in latest_period_series.index
        }
    except Exception:
        return {}

def get_company_snapshot_yf(symbol: str) -> Dict[str, Any]:
    """
    Build a compact snapshot for a listed company using yfinance.
    yfinance manages its own session (curl_cffi).
    """
    yf_ticker = yf.Ticker(symbol)

    # Market cap
    market_capitalization = safe_get_fast_info(yf_ticker, "market_cap")
    if market_capitalization is None:
        market_capitalization = safe_get_info(yf_ticker, "marketCap")

    # P/E ratio
    price_to_earnings = safe_get_fast_info(yf_ticker, "pe")
    if price_to_earnings is None:
        pe_a = safe_get_info(yf_ticker, "trailingPE")
        pe_b = safe_get_info(yf_ticker, "forwardPE")
        price_to_earnings = pe_a if pe_a is not None else pe_b

    enterprise_value = safe_get_info(yf_ticker, "enterpriseValue")

    # Financials (wrap attribute access with backoff)
    def get_fin_df(attr_name: str):
        try:
            return with_backoff(getattr, yf_ticker, attr_name, max_retries=3, base_sleep=1.5)
        except requests.HTTPError as e:
            if getattr(e.response, "status_code", None) == 429:
                print(f"[WARN] 429 when fetching {attr_name} for {symbol}")
            return None
        except Exception:
            return None

    annual_financials_df = get_fin_df("financials")
    latest_annual_financials = latest_financial_row(annual_financials_df)

    if not latest_annual_financials:
        quarterly_financials_df = get_fin_df("quarterly_financials")
        latest_annual_financials = latest_financial_row(quarterly_financials_df)

    # Extract revenue and net income using common alternate labels
    total_revenue_value = None
    for revenue_key in ("Total Revenue", "TotalRevenue", "Revenue"):
        if revenue_key in latest_annual_financials:
            total_revenue_value = latest_annual_financials[revenue_key]
            break

    net_income_value = None
    for net_income_key in ("Net Income", "NetIncome", "Net Income Applicable To Common Shares"):
        if net_income_key in latest_annual_financials:
            net_income_value = latest_annual_financials[net_income_key]
            break

    # EBITDA may be present in info or as 'Ebitda' in financials
    ebitda_value = safe_get_info(yf_ticker, "ebitda")
    if ebitda_value is None and "Ebitda" in latest_annual_financials:
        ebitda_value = latest_annual_financials["Ebitda"]

    company_snapshot: Dict[str, Any] = {
        "symbol": symbol,
        "market_cap": market_capitalization,
        "pe": price_to_earnings,
        "enterprise_value": enterprise_value,
        "ebitda": ebitda_value,
        "revenue": total_revenue_value,
        "net_income": net_income_value,
        "cap_bucket": cap_bucket(market_capitalization),
        "as_of": int(time.time()),
    }
    return company_snapshot


# ---------------- Region helpers ----------------

def symbol_root(sym: Optional[str]) -> str:
    s = (sym or "").strip().upper()
    return s.split(".", 1)[0] if "." in s else s

def is_region_fit(exchange: Optional[str], region: Optional[str]) -> bool:
    ex = normalize_exchange(exchange)
    allow = REGION_EXCHANGE_PREFS.get(region, REGION_EXCHANGE_PREFS.get(None, []))
    return ex in allow if allow else True


# ---------------- Public API ----------------

def get_company_symbol(company_name: str, region: Optional[str] = None, finnhub_top_k: int = 3, force_refresh: bool = False) -> Optional[str]:
    """
    Yahoo-first, Finnhub-verify, then last-resort scorer.
    Caches by normalized company name (+ region).
    """
    cache_key = normalize_name(company_name) + (f"|{region}" if region else "")

    # Cache read
    if not force_refresh and cache_key in symbol_cache:
        cached = symbol_cache[cache_key]
        if isinstance(cached, str):
            return cached
        if isinstance(cached, dict):
            return cached.get("symbol")

    # Try yahoo first
    yahoo_candidates = lookup_symbol_company_yahoo(company_name)
    best_yahoo_candidate: Optional[Dict[str, Any]] = None
    top_score = 0.0

    if yahoo_candidates:
        scores = [float(c.get("match_score") or 0.0) for c in yahoo_candidates]
        top_score = max(scores) if scores else 0.0

        best_yahoo_candidate = yahoo_candidates[0]
        best_yahoo_name = best_yahoo_candidate.get("name") or ""
        best_yahoo_score = float(best_yahoo_candidate.get("match_score") or 0.0)
        yahoo_name_sim = name_similarity_score(company_name, best_yahoo_name)
        acceptance_bar = top_score * 0.98 if top_score else 0.0

        if (
            ((top_score > 0 and best_yahoo_score >= acceptance_bar) or yahoo_name_sim >= 0.60)
            and is_region_fit(best_yahoo_candidate.get("exchange"), region)
        ):
            symbol_value = best_yahoo_candidate.get("symbol")
            symbol_cache[cache_key] = symbol_value or {"symbol": None, "as_of": int(time.time())}
            save_cache(symbol_cache)
            return symbol_value

    # Finnhub fallback ---
    finnhub_top_candidates = lookup_symbol_company_finnhub(company_name)[:finnhub_top_k]

    if best_yahoo_candidate:
        yahoo_root = symbol_root(best_yahoo_candidate.get("symbol"))
        yahoo_name = best_yahoo_candidate.get("name") or ""
        for f in finnhub_top_candidates:
            f_root = symbol_root(f.get("symbol"))
            if (yahoo_root and f_root and yahoo_root == f_root) or name_similarity_score(yahoo_name, f.get("name") or "") >= 0.70:
                yf_ok = is_region_fit(best_yahoo_candidate.get("exchange"), region)
                f_ok  = is_region_fit(f.get("exchange"), region)
                symbol_value = (f.get("symbol") if (f_ok and not yf_ok) else best_yahoo_candidate.get("symbol")) if (yf_ok or f_ok) else best_yahoo_candidate.get("symbol")
                symbol_cache[cache_key] = symbol_value or {"symbol": None, "as_of": int(time.time())}
                save_cache(symbol_cache)
                return symbol_value

    # Last resort: score combined candidates
    combined: List[Dict[str, Any]] = []
    for src in (yahoo_candidates or []):
        c = dict(src)
        c["exchange"] = normalize_exchange(c.get("exchange"))
        combined.append(c)
    for src in (finnhub_top_candidates or []):
        c = dict(src)
        c["exchange"] = normalize_exchange(c.get("exchange"))
        combined.append(c)

    # dedupe by symbol root
    seen = set()
    unique: List[Dict[str, Any]] = []
    for c in combined:
        sr = symbol_root(c.get("symbol"))
        if sr and sr not in seen:
            unique.append(c)
            seen.add(sr)

    allowed_exchanges = REGION_EXCHANGE_PREFS.get(region)
    best = choose_best_symbol_global(unique, query_name=company_name, allowed_exchanges=allowed_exchanges)

    symbol_value = best.get("symbol") if best else None
    symbol_cache[cache_key] = symbol_value or {"symbol": None, "as_of": int(time.time())}
    save_cache(symbol_cache)
    return symbol_value

def is_probably_non_listable(name: str) -> bool:
    s = normalize_text(name)
    return any(kw in s.split() for kw in NON_LISTABLE_KEYWORDS)

def get_company_info(company_name: str, region: Optional[str] = None) -> dict:
    print(f"Getting information of {company_name}")
    if is_probably_non_listable(company_name):
        return {"name": company_name, "symbol": None, "note": "non-listable or generic entity"}
    print(f"    - Getting symbol of {company_name}")
    symbol = get_company_symbol(company_name, region=region)
    print(f"Got symbol: {symbol}")
    if not symbol:
        return {"name": company_name, "symbol": None, "note": "no reliable listing found"}
    snapshot = get_company_snapshot_yf(symbol)
    snapshot["name"] = company_name
    return snapshot


# ---------------- Main ----------------

if __name__ == "__main__":
    print_system_info()
    test_pairs = [
        ("Diamondback Energy", "US"),
        ("Tesco", "Europe"),
        ("ASML", "Europe"),
        ("HSBC Bank Malta", "Europe"),
    ]
    for nm, rg in test_pairs:
        try:
            print(get_company_info(nm, rg), "\n")
        except Exception as e:
            print(nm, rg, "ERR:", repr(e))
