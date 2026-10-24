"""Download 5 years of dividend-adjusted daily prices from Interactive Brokers.

Needs TWS or IB Gateway running locally with the API enabled
(Configure > API > Settings > "Enable ActiveX and Socket Clients").

    python -m frontier.ibkr_fetch                 # full universe, TWS paper port 7497
    python -m frontier.ibkr_fetch --port 4002     # IB Gateway paper
    python -m frontier.ibkr_fetch --etfs-only     # skip the S&P 500 stocks

Each symbol is cached under data/cache/, so an interrupted run resumes where it stopped.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections.abc import Callable

import pandas as pd

from .data import DATA_DIR, FULL_META, FULL_PRICES
from .universe import build_universe

CACHE_DIR = DATA_DIR / "cache"
# Set IBKR_PORT=4002 for IB Gateway paper (and IBKR_HOST when Gateway runs elsewhere, e.g. Windows
# from WSL), so the app's refresh button finds it too.
DEFAULT_HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("IBKR_PORT", 7497))


def _ib_symbol(symbol: str) -> str:
    # Wikipedia writes share classes as BRK.B; IBKR expects BRK B.
    return symbol.replace(".", " ").replace("-", " ")


def fetch_symbol(ib, symbol: str, years: int) -> pd.Series | None:
    from ib_async import Stock

    contract = Stock(_ib_symbol(symbol), "SMART", "USD")
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        return None
    bars = ib.reqHistoricalData(
        qualified[0],
        endDateTime="",  # ADJUSTED_LAST only works with an empty end date
        durationStr=f"{years} Y",
        barSizeSetting="1 day",
        whatToShow="ADJUSTED_LAST",
        useRTH=True,
        formatDate=1,
    )
    if not bars:
        return None
    return pd.Series({pd.Timestamp(b.date): b.close for b in bars}, name=symbol)


def fetch_all(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, client_id: int = 17, years: int = 5,
              include_sp500: bool = True, refresh: bool = False,
              progress: Callable[[int, int, str], None] | None = None) -> pd.DataFrame:
    from ib_async import IB

    # Streamlit runs scripts in a worker thread that has no asyncio loop, which ib_async needs.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    try:
        universe = build_universe(include_sp500)
    except OSError as exc:
        raise RuntimeError(f"Couldn't download the S&P 500 list from Wikipedia ({exc}). Try --etfs-only.") from exc
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    ib = IB()
    ib.connect(host, port, clientId=client_id, readonly=True)
    failed = []
    try:
        for i, symbol in enumerate(universe["symbol"], start=1):
            if progress:
                progress(i, len(universe), symbol)
            path = CACHE_DIR / f"{symbol}.parquet"
            if path.exists() and not refresh:
                continue
            try:
                series = fetch_symbol(ib, symbol, years)
            except Exception as exc:  # one bad contract shouldn't stop a 550-symbol run
                print(f"{symbol}: {exc}")
                series = None
            if series is None:
                failed.append(symbol)
                continue
            series.to_frame().to_parquet(path)
            time.sleep(0.5)  # stay well inside IBKR's historical data pacing limits
    finally:
        ib.disconnect()

    frames = [pd.read_parquet(CACHE_DIR / f"{s}.parquet") for s in universe["symbol"]
              if (CACHE_DIR / f"{s}.parquet").exists()]
    prices = pd.concat(frames, axis=1).sort_index()
    prices.index.name = "date"
    prices.to_parquet(FULL_PRICES)
    universe[universe["symbol"].isin(prices.columns)].to_csv(FULL_META, index=False)
    if failed:
        print(f"No data for {len(failed)} symbols: {', '.join(failed)}")
    return prices


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=DEFAULT_HOST, help="default: $IBKR_HOST or 127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="7497 TWS paper, 7496 TWS live, 4002/4001 Gateway (default: $IBKR_PORT or 7497)")
    parser.add_argument("--client-id", type=int, default=17)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--etfs-only", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="ignore the cache and download everything again")
    args = parser.parse_args()
    prices = fetch_all(args.host, args.port, args.client_id, args.years, not args.etfs_only, args.refresh,
                       progress=lambda i, n, s: print(f"[{i}/{n}] {s}", end="\r"))
    print(f"\nSaved {prices.shape[1]} assets x {prices.shape[0]} days to {FULL_PRICES}")


if __name__ == "__main__":
    main()
