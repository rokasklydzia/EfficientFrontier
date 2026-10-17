"""Loading prices and turning them into annualised return statistics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FULL_PRICES = DATA_DIR / "prices_daily.parquet"
FULL_META = DATA_DIR / "universe.csv"
SAMPLE_PRICES = DATA_DIR / "sample_prices_monthly.csv"
SAMPLE_META = DATA_DIR / "sample_universe.csv"


TBILL_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"


def latest_tbill_rate() -> float | None:
    """Latest 3-month T-bill yield from FRED as a decimal, or None if it can't be fetched."""
    try:
        rates = pd.read_csv(TBILL_URL, na_values=".").dropna()
        return float(rates.iloc[-1, 1]) / 100
    except Exception:
        return None


def load_prices() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Return (prices, metadata, source label). Prefers the full IBKR download over the bundled sample."""
    if FULL_PRICES.exists():
        prices = pd.read_parquet(FULL_PRICES)
        meta = pd.read_csv(FULL_META) if FULL_META.exists() else _default_meta(prices.columns)
        return prices.sort_index(), meta, "IBKR daily (adjusted)"
    prices = pd.read_csv(SAMPLE_PRICES, index_col="date", parse_dates=True)
    return prices.sort_index(), pd.read_csv(SAMPLE_META), "Bundled sample (monthly, not dividend-adjusted)"


def _default_meta(symbols) -> pd.DataFrame:
    return pd.DataFrame({"symbol": list(symbols), "name": list(symbols), "asset_class": "Unknown", "sector": ""})


def periods_per_year(index: pd.DatetimeIndex) -> int:
    """Infer the sampling frequency from the median spacing between observations."""
    days = np.median(np.diff(index.values).astype("timedelta64[D]").astype(float))
    if days <= 1.5:
        return 252
    if days <= 8:
        return 52
    return 12


def clean_prices(prices: pd.DataFrame, min_coverage: float = 0.95, max_gap: int = 5) -> pd.DataFrame:
    """Drop assets with too little history, fill short gaps, then keep only dates every asset has."""
    prices = prices.dropna(how="all")
    coverage = prices.notna().mean()
    prices = prices.loc[:, coverage >= min_coverage]
    prices = prices.ffill(limit=max_gap)
    return prices.dropna(how="any")


@dataclass
class Moments:
    mu: pd.Series  # annualised arithmetic mean of simple returns
    cov: pd.DataFrame  # annualised covariance of simple returns
    returns: pd.DataFrame
    periods: int


def estimate_moments(prices: pd.DataFrame) -> Moments:
    # Simple (not log) returns, because portfolio returns are linear in simple asset returns.
    returns = prices.pct_change().dropna(how="any")
    periods = periods_per_year(prices.index)
    return Moments(mu=returns.mean() * periods, cov=returns.cov() * periods, returns=returns, periods=periods)
