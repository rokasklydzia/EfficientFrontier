"""Asset universe: S&P 500 stocks plus bond and commodity ETFs."""

from __future__ import annotations

import io
import urllib.request

import pandas as pd

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Core equity index ETFs, kept alongside single stocks so the equity class has broad benchmarks too.
EQUITY_ETFS = {
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000",
    "EFA": "Developed ex-US",
    "EEM": "Emerging markets",
    "VNQ": "US REITs",
}

BOND_ETFS = {
    "BIL": "T-bills 1-3m",
    "SHY": "Treasuries 1-3y",
    "IEI": "Treasuries 3-7y",
    "IEF": "Treasuries 7-10y",
    "TLT": "Treasuries 20y+",
    "TIP": "TIPS",
    "AGG": "US aggregate",
    "LQD": "IG corporate",
    "HYG": "High yield corporate",
    "MUB": "Municipal",
    "MBB": "Mortgage-backed",
    "EMB": "EM sovereign USD",
    "BNDX": "International aggregate (hedged)",
}

COMMODITY_ETFS = {
    "GLD": "Gold",
    "SLV": "Silver",
    "PPLT": "Platinum",
    "CPER": "Copper",
    "USO": "WTI crude oil",
    "BNO": "Brent crude oil",
    "UNG": "Natural gas",
    "DBA": "Agriculture",
    "DBB": "Base metals",
    "DBC": "Broad commodities",
    "PDBC": "Broad commodities (no K-1)",
    "GSG": "S&P GSCI",
}


def fetch_sp500() -> pd.DataFrame:
    """Current S&P 500 constituents from Wikipedia: symbol, name, sector."""
    req = urllib.request.Request(SP500_URL, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    table = pd.read_html(io.StringIO(html), attrs={"id": "constituents"})[0]
    return pd.DataFrame(
        {
            "symbol": table["Symbol"].str.strip(),
            "name": table["Security"],
            "asset_class": "Equity",
            "sector": table["GICS Sector"],
        }
    )


def etf_universe() -> pd.DataFrame:
    rows = []
    for asset_class, etfs in (("Equity", EQUITY_ETFS), ("Bond", BOND_ETFS), ("Commodity", COMMODITY_ETFS)):
        for symbol, name in etfs.items():
            rows.append({"symbol": symbol, "name": name, "asset_class": asset_class, "sector": f"{asset_class} ETF"})
    return pd.DataFrame(rows)


def build_universe(include_sp500: bool = True) -> pd.DataFrame:
    parts = [etf_universe()]
    if include_sp500:
        parts.append(fetch_sp500())
    return pd.concat(parts, ignore_index=True).drop_duplicates("symbol").reset_index(drop=True)
