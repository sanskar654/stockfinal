"""
NIFTY 50 Ticker Validation & Alias Resolution Utility.

Ensures only valid NIFTY 50 constituents and supported index tickers
are processed by the ML service. Resolves user input variations
(e.g. "Tata Steel" -> "TATASTEEL", "Infosys" -> "INFY", "NIFTY" -> "NIFTY50").
"""
from __future__ import annotations

NIFTY50_TICKERS = {
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
    "BAJAJFINSV", "BAJFINANCE", "BEL", "BHARTIARTL", "BPCL", "BRITANNIA", "CIPLA",
    "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK",
    "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN",
    "SHRIRAMFIN", "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT",
    "ULTRACEMCO", "WIPRO"
}

# Index tickers supported by the platform
INDEX_TICKERS = {"NIFTY50", "BANKNIFTY", "FINNIFTY"}

# Maps canonical index ticker to FYERS symbol and yfinance symbol
INDEX_FYERS_MAP = {
    "NIFTY50":    {"fyers": "NSE:NIFTY50-INDEX",    "yfinance": "^NSEI",     "name": "NIFTY 50 Index"},
    "BANKNIFTY":  {"fyers": "NSE:NIFTYBANK-INDEX",  "yfinance": "^NSEBANK",  "name": "Bank NIFTY Index"},
    "FINNIFTY":   {"fyers": "NSE:FINNIFTY-INDEX",   "yfinance": "NIFTY_FIN_SERVICE.NS", "name": "FIN NIFTY Index"},
}

# Alias mapping for user inputs
ALIAS_MAP = {
    "TATA STEEL": "TATASTEEL",
    "TATASTEEL": "TATASTEEL",
    "BAJAJ AUTO": "BAJAJ-AUTO",
    "BAJAJ-AUTO": "BAJAJ-AUTO",
    "BAJAJ FINANCE": "BAJFINANCE",
    "BAJ FINANCE": "BAJFINANCE",
    "BAJAJ FINSERV": "BAJAJFINSV",
    "BHARAT ELECTRONICS": "BEL",
    "BHARAT PETROLEUM": "BPCL",
    "AIRTEL": "BHARTIARTL",
    "BHARTI AIRTEL": "BHARTIARTL",
    "COAL INDIA": "COALINDIA",
    "DR REDDY": "DRREDDY",
    "DR REDDYS": "DRREDDY",
    "DR. REDDY": "DRREDDY",
    "EICHER MOTORS": "EICHERMOT",
    "EICHER": "EICHERMOT",
    "HCL TECH": "HCLTECH",
    "HCL TECHNOLOGIES": "HCLTECH",
    "HDFC BANK": "HDFCBANK",
    "HDFC LIFE": "HDFCLIFE",
    "HERO MOTOCORP": "HEROMOTOCO",
    "HERO HONDA": "HEROMOTOCO",
    "HINDUSTAN UNILEVER": "HINDUNILVR",
    "HUL": "HINDUNILVR",
    "ICICI BANK": "ICICIBANK",
    "INDUSIND BANK": "INDUSINDBK",
    "INFOSYS": "INFY",
    "INFY": "INFY",
    "JIO FINANCIAL": "JIOFIN",
    "JIOFIN": "JIOFIN",
    "JSW STEEL": "JSWSTEEL",
    "KOTAK BANK": "KOTAKBANK",
    "KOTAK MAHINDRA BANK": "KOTAKBANK",
    "LARSEN & TOUBRO": "LT",
    "LARSEN AND TOUBRO": "LT",
    "L&T": "LT",
    "LT": "LT",
    "MAHINDRA & MAHINDRA": "M&M",
    "MAHINDRA AND MAHINDRA": "M&M",
    "M&M": "M&M",
    "MARUTI SUZUKI": "MARUTI",
    "MARUTI": "MARUTI",
    "NESTLE INDIA": "NESTLEIND",
    "NESTLE": "NESTLEIND",
    "POWER GRID": "POWERGRID",
    "POWERGRID": "POWERGRID",
    "RELIANCE INDUSTRIES": "RELIANCE",
    "RIL": "RELIANCE",
    "SBI": "SBIN",
    "STATE BANK OF INDIA": "SBIN",
    "SBI LIFE": "SBILIFE",
    "SHRIRAM FINANCE": "SHRIRAMFIN",
    "SUN PHARMA": "SUNPHARMA",
    "SUN PHARMACEUTICALS": "SUNPHARMA",
    "TATA CONSUMER": "TATACONSUM",
    "TATA CONSUMER PRODUCTS": "TATACONSUM",
    "TATA MOTORS": "TATAMOTORS",
    "TECH MAHINDRA": "TECHM",
    "TECH M": "TECHM",
    "ULTRATECH CEMENT": "ULTRACEMCO",
    "ULTRA TECH CEMENT": "ULTRACEMCO",
    "WIPRO": "WIPRO",
    "APOLLO HOSPITALS": "APOLLOHOSP",
    "ASIAN PAINTS": "ASIANPAINT",
    "AXIS BANK": "AXISBANK",
    # Index aliases
    "NIFTY": "NIFTY50",
    "NIFTY 50": "NIFTY50",
    "NIFTY50": "NIFTY50",
    "BANK NIFTY": "BANKNIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "BANK-NIFTY": "BANKNIFTY",
    "NIFTYBANK": "BANKNIFTY",
    "FIN NIFTY": "FINNIFTY",
    "FINNIFTY": "FINNIFTY",
    "NIFTY FIN": "FINNIFTY",
}


def is_index_ticker(ticker: str) -> bool:
    """Returns True if the ticker is a supported index."""
    return ticker.strip().upper() in INDEX_TICKERS


def normalize_and_validate_ticker(ticker_input: str) -> str:
    """Normalizes ticker string and validates against the NIFTY 50 universe
    or supported index tickers.

    Raises ValueError if ticker is not in NIFTY 50 universe or supported indices.
    """
    if not ticker_input or not isinstance(ticker_input, str):
        raise ValueError("Ticker must be a non-empty string.")

    cleaned = ticker_input.strip().upper()
    cleaned = cleaned.replace("NSE:", "").replace("-EQ", "").replace("-INDEX", "").strip()

    # 1. Direct match in canonical stock universe
    if cleaned in NIFTY50_TICKERS:
        return cleaned

    # 2. Direct match in index tickers
    if cleaned in INDEX_TICKERS:
        return cleaned

    # 3. Match in alias map (covers both stock and index aliases)
    if cleaned in ALIAS_MAP:
        resolved = ALIAS_MAP[cleaned]
        if resolved in NIFTY50_TICKERS or resolved in INDEX_TICKERS:
            return resolved

    # 4. Try removing spaces (e.g. "TATA STEEL" -> "TATASTEEL")
    no_spaces = cleaned.replace(" ", "")
    if no_spaces in NIFTY50_TICKERS:
        return no_spaces
    if no_spaces in INDEX_TICKERS:
        return no_spaces

    # 5. If not found, raise explicit error
    all_supported = sorted(list(NIFTY50_TICKERS) + list(INDEX_TICKERS))
    raise ValueError(
        f"'{ticker_input}' is not a valid ticker. "
        f"Supported tickers include NIFTY 50 stocks and index instruments "
        f"(NIFTY50, BANKNIFTY, FINNIFTY).\n"
        f"All supported tickers: {', '.join(all_supported)}"
    )

