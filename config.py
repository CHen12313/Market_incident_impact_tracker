import os

NEWS_API_BACKUP = "***REMOVED_NEWS_API_BACKUP***"
NEWS_API_BACKUP2 = "***REMOVED_NEWS_API_BACKUP2***"
NEWS_API_BACKUP3 = "***REMOVED_NEWS_API_BACKUP3***"
NEWS_API_BACKUP4 = "***REMOVED_NEWS_API_BACKUP4***"
NEWS_API_BACKUP5 = "***REMOVED_NEWS_API_BACKUP5***"
NEWS_API_BACKUP6 = "***REMOVED_NEWS_API_BACKUP6***"
NEWS_API_KEY = "***REMOVED_NEWS_API_KEY***"
OPENAI_API_KEY = "***REMOVED_OPENAI_API_KEY***"
ALPHA_VANTAGE_API_KEY = "***REMOVED_ALPHA_VANTAGE_API_KEY***"
FINNHUB_API_KEY = "***REMOVED_FINNHUB_API_KEY***"

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

