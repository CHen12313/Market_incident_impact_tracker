import os
from pathlib import Path
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.is_file():
    from dotenv import load_dotenv

    load_dotenv(env_file)

NEWS_API_BACKUP = os.environ.get("NEWS_API_BACKUP", "")
NEWS_API_BACKUP2 = os.environ.get("NEWS_API_BACKUP2", "")
NEWS_API_BACKUP3 = os.environ.get("NEWS_API_BACKUP3", "")
NEWS_API_BACKUP4 = os.environ.get("NEWS_API_BACKUP4", "")
NEWS_API_BACKUP5 = os.environ.get("NEWS_API_BACKUP5", "")
NEWS_API_BACKUP6 = os.environ.get("NEWS_API_BACKUP6", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

# Time Settings
NEWS_LOOKBACK_DAYS = 7  # Number of days to look back for news 

# News Categories
TMT_CATEGORIES = [
    "technology",          # broad umbrella
    "software",
    "semiconductors",
    "telecommunications",
    "artificial intelligence"
]

ENERGY_CATEGORIES = [
    "energy",              # broad umbrella
    "oil",
    "natural gas",
    "renewable",           # solar, wind, etc.
    "utilities"
]

HEALTHCARE_CATEGORIES = [
    "Healthcare mergers and acquisitions",
    "healthcare",
    "pharmaceuticals",
    "biotechnology",
    "healthcare technology"
]

INDUSTRIAL_CATEGORIES = [
    "manufacturing",
    "capital goods",
    "transportation",
    "construction",
    "aerospace"
]

CONSUMER_CATEGORIES = [
    "retail",
    "consumer goods",
    "food & beverage",
    "apparel",
    "e-commerce"
]

SECTOR_DEAL_TERMS = {
    "healthcare": [
        # Core M&A
        "merger", "acquisition", "buyout", "stake", "takeover", "deal", "transaction",
        "investment", "invests", "backs", "funding", "financing", "raises", "capital raise",

        # Licensing & Partnerships
        "licensing", "collaboration", "alliance", "joint venture", "strategic partnership",

        # Healthcare-specific
        "drug approval", "FDA approval", "clinical trial", "phase 1", "phase 2", "phase 3",
        "biotech", "pharma", "life sciences", "medtech", "medical device"
    ],

    "tmt": [  # (Technology, Media, Telecom)
        # Core M&A / funding
        "merger", "acquisition", "acquire", "buys", "takeover", "buyout", "stake",
        "deal", "transaction", "investment", "invests", "funding", "financing", "capital raise",
        "venture capital", "private equity", "series A", "series B", "series C",
        "IPO", "listing", "SPAC",

        # Sector-specific
        "startup", "scale-up", "unicorn", "tech giant", "software", "AI", "cloud",
        "semiconductor", "chipmaker", "telecom", "5G", "streaming", "media rights"
    ],

    "energy": [
        # Core M&A / finance
        "merger", "acquisition", "buyout", "stake", "equity", "takeover", "deal",
        "transaction", "investment", "invests", "capital raise", "financing",

        # Partnerships / restructuring
        "joint venture", "partnership", 
        "divestiture", "asset purchase", "spinoff",

        # Energy-specific
        "oil & gas", "renewable", "solar", "nuclear", "LNG",
        "offshore", "power plant",  "decarbonization"
    ],

    "industrial": [
        # Core M&A
        "merger", "acquisition", "buyout", "stake", "takeover", "deal",
        "transaction", "investment", "invests", "capital raise",

        # Partnerships / projects
        "joint venture", "JV", "partnership", "strategic alliance",
        "plant expansion", "factory construction", "facility investment",
        "infrastructure project", "engineering contract", "supply chain deal",
        "logistics partnership", "defense contract", "aerospace order"
    ],

    "consumer": [
        # Core M&A / finance
        "merger", "acquisition", "buyout", "stake", "takeover", "deal",
        "transaction", "investment", "invests", "capital raise", "financing",

        # Consumer-specific growth
        "brand acquisition", "retail expansion", "store opening", "franchise deal",
        "product launch", "new collection", "e-commerce investment",
        "food & beverage", "luxury", "fashion", "consumer goods giant", "CPG"
    ],

    "_default": [
        "merger", "acquisition", "acquire", "buys", "takeover", "deal",
        "investment", "invests", "funding", "financing", "capital raise"
    ]
}

REGION_ANCHORS = {
    "Europe": [
        "Europe", "European Union", "EU", "Eurozone",
        "European Commission", "DG COMP", "ECB", "ESMA", "CMA",
        "Euro Stoxx", "DAX", "CAC", "FTSE"
    ],
    "APAC": [
        "Asia Pacific", "APAC", "ASEAN", "Asean Bloc",
        "China", "Japan", "South Korea", "Australia", "New Zealand",
        "HKEX", "SGX", "Nikkei", "Hang Seng"
    ]
}

# Incident types this pipeline searches for (DATA_CONTRACT.md's `event_type`,
# minus "other" — NewsCollector doesn't search for that one).
ALL_EVENT_TYPES = ["merger", "breach", "recall", "outage", "lawsuit", "regulation"]
DEFAULT_DAYS_BACK = 3

# Search terms per incident type, same role as SECTOR_DEAL_TERMS but keyed by
# event_type instead of sector. NewsCollector ORs these together as its query.
INCIDENT_TERMS = {
    "merger": [
        "merger", "acquisition", "acquire", "buyout", "takeover", "stake",
        "deal", "transaction"
    ],
    "breach": [
        "data breach", "cyberattack", "cyber attack", "hack", "hacked",
        "ransomware", "security breach", "data leak", "exposed data"
    ],
    "recall": [
        "recall", "recalled", "product recall", "safety recall", "defect",
        "withdrawn from market"
    ],
    "outage": [
        "outage", "service disruption", "downtime", "system failure",
        "went down", "service interruption"
    ],
    "lawsuit": [
        "lawsuit", "sued", "litigation", "class action", "legal action",
        "court filing"
    ],
    "regulation": [
        "fine", "fined", "regulatory action", "sanctions", "investigation",
        "regulator", "compliance violation", "penalty"
    ],
    "_default": ["incident", "controversy", "crisis"]
}

# Lowercase company name -> ticker. TickerResolver checks this before calling
# get_company_symbol(), for demo companies whose real-world lookup is flaky
# or fictional (mock events). Empty until the demo events are picked.
DEMO_TICKER_OVERRIDES: dict[str, str] = {}
