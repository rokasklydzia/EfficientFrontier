# Efficient Frontier

A Streamlit app that builds the long-only Markowitz efficient frontier across US stocks, bonds and commodities from 5 years of Interactive Brokers price history.

## What it does

- **Universe:** S&P 500 constituents (from Wikipedia), 6 equity index ETFs, 13 bond ETFs (T-bills through long Treasuries, TIPS, IG, HY, munis, MBS, EM, international) and 12 commodity ETFs (precious and base metals, oil, gas, agriculture, broad baskets). That's about 530 assets in total. The lists are in `frontier/universe.py`.
- **Data:** daily `ADJUSTED_LAST` bars from IBKR. These are adjusted for dividends and splits, which matters for bond ETFs, since most of their return is coupons.
- **Model:** simple returns, annualised sample mean and covariance, long-only weights with an optional per-asset cap. The app shows:
  - the frontier, traced by minimising variance at evenly spaced target returns;
  - the global minimum-variance portfolio;
  - the tangency (maximum-Sharpe) portfolio, found through the convex reformulation `min y'Σy s.t. (μ − r_f)'y = 1`, then `w = y / Σy`;
  - the capital market line.
- **Risk-free rate:** defaults to the latest 3-month T-bill yield from FRED (`DTB3`), and falls back to 4% when offline.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Get the full dataset from IBKR

1. Start TWS or IB Gateway and log in (paper is fine).
2. Enable the API under *Configure → API → Settings → Enable ActiveX and Socket Clients*.
3. Run:

```bash
python -m frontier.ibkr_fetch               # TWS paper, port 7497
python -m frontier.ibkr_fetch --port 7496   # TWS live
python -m frontier.ibkr_fetch --port 4002   # IB Gateway paper (4001 for live)
python -m frontier.ibkr_fetch --etfs-only   # skip the S&P 500 stocks
```

The download takes a while for about 530 symbols. Each symbol is cached in `data/cache/`, so an interrupted run picks up where it stopped. Pass `--refresh` to download everything again. The result is written to `data/prices_daily.parquet`. You can also start the download from the app's **Refresh from IBKR** button.

US stocks and ETFs need an IBKR market data subscription for historical bars. Without one, those symbols are skipped and listed at the end of the run.

## Run the app

```bash
streamlit run app.py
```

If `data/prices_daily.parquet` doesn't exist, the app falls back to `data/sample_prices_monthly.csv`. That file holds 15 ETFs with monthly closes from October 2021 to October 2026, pulled through the IBKR connector. **The sample is not dividend-adjusted**, so bond returns in it are understated by roughly their yield. Use it only to try the app out.

The sidebar lets you filter by asset class, change the date window and minimum history coverage, set the risk-free rate and max weight per asset, and choose how many frontier points to draw.

## Tests

```bash
pytest
```

The tests check that:
- weights are long-only, respect the cap and sum to 1;
- the frontier is monotone in risk and return;
- no single asset sits above the frontier;
- the minimum-variance portfolio has lower volatility than every asset;
- the tangency portfolio has the highest Sharpe ratio on the frontier;
- the tangency weights match the closed-form `Σ⁻¹(μ − r_f)` when no constraint binds.

## Caveats

- **Estimation error:** sample means are very noisy, so unconstrained Markowitz weights tend to concentrate in the few assets with the best past returns. The max weight cap is the simplest control for this. With about 530 assets and about 1,260 daily observations, the covariance matrix is invertible but poorly conditioned.
- **Survivorship bias:** the stock list is today's S&P 500, so companies that dropped out over the last 5 years are missing.
- **In-sample only:** the frontier describes the past window. It is not a forecast.
