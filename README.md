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

The fetch script talks to IB Gateway or Trader Workstation (TWS) running on your own machine through the IBKR socket API. IB Gateway is the lighter option: it has no charts or order screens, only a login window and the API. Use TWS if you also want to look at the account.

### 1. Install IB Gateway (or TWS)

Download the **stable** installer for your OS. Both bundle their own Java, so nothing else is needed.

- IB Gateway: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
- TWS: https://www.interactivebrokers.com/en/trading/tws.php

| OS | Install |
|---|---|
| Windows | Run the `.exe` installer and start *IB Gateway* from the Start menu. |
| macOS | Open the `.dmg`, run the installer, then start *IB Gateway* from Applications. If macOS blocks it, allow it under *System Settings → Privacy & Security*. |
| Linux | `chmod +x ibgateway-stable-standalone-linux-x64.sh && ./ibgateway-stable-standalone-linux-x64.sh`, then start it from `~/Jts/ibgateway/<version>/ibgateway`. |

### 2. Log in to the paper account

Select **IB API** (not FIX CTCI) and **Paper Trading**, and log in with your *paper* username. You find it in the IBKR client portal under *Settings → Account Settings → Paper Trading Account*, where you can also reset its password.

On the same page, turn on **Share real-time market data subscriptions with paper trading account**. Without that, the paper login has no market data permissions and historical requests for US stocks and ETFs fail. The share takes effect from the next day.

### 3. Configure the API

IB Gateway: *Configure → Settings → API → Settings*. TWS: *File (or Edit) → Global Configuration → API → Settings*.

| Setting | Value |
|---|---|
| Enable ActiveX and Socket Clients | on (TWS only; Gateway always has it on) |
| Read-Only API | on (the script connects with `readonly=True` and never places orders) |
| Socket port | 4002 Gateway paper, 4001 Gateway live, 7497 TWS paper, 7496 TWS live |
| Allow connections from localhost only | on |
| Trusted IPs | `127.0.0.1` |

Click **Apply** and **OK**. Gateway and TWS log you out once a day; set the daily restart time under *Lock and Exit* so it doesn't happen mid-download.

### 4. Download the prices

The script connects with client id 17 to `127.0.0.1` (or `IBKR_HOST`), on port 7497 (TWS paper) unless `IBKR_PORT` is set.

```bash
python -m frontier.ibkr_fetch                 # TWS paper, port 7497
python -m frontier.ibkr_fetch --port 4002     # IB Gateway paper (4001 for live)
python -m frontier.ibkr_fetch --port 7496     # TWS live
python -m frontier.ibkr_fetch --etfs-only     # skip the S&P 500 stocks; good for a first test
```

To use Gateway everywhere, including the app's **Refresh from IBKR** button, set the port once:

```bash
export IBKR_PORT=4002        # macOS / Linux
$env:IBKR_PORT = "4002"      # Windows PowerShell
```

### Running the script in WSL with Gateway on Windows

Inside WSL, `127.0.0.1` is the Linux VM, not Windows, so the script gets `ConnectionRefusedError`. Point it at the Windows host and let Gateway accept WSL's address:

1. In Gateway's API settings, untick **Allow connections from localhost only** and add WSL's own address to **Trusted IPs**. Get that address in WSL with `hostname -I | awk '{print $1}'`. It can change after a reboot, so update it if connections start timing out.
2. Set the host to the Windows side of WSL's network:

```bash
export IBKR_HOST=$(ip route | awk '/default/ {print $3}')
export IBKR_PORT=4001        # or 4002 for paper
python -m frontier.ibkr_fetch --etfs-only
```

A `TimeoutError` (rather than connection refused) means the connection reached Gateway but it didn't accept it: recheck step 1.

The download takes a while for about 530 symbols. Each symbol is cached in `data/cache/`, so an interrupted run picks up where it stopped. Pass `--refresh` to download everything again. The result is written to `data/prices_daily.parquet`.

US stocks and ETFs need an IBKR market data subscription for historical bars (the *US Securities Snapshot and Futures Value Bundle* covers them). Without one, those symbols are skipped and listed at the end of the run.

### Troubleshooting

| Message | Cause and fix |
|---|---|
| `ConnectionRefusedError` / `API connection failed` | Gateway or TWS isn't running or logged in, or the port is wrong. Check the socket port in the API settings and pass the same `--port`. |
| `TimeoutError` right after connecting | A login dialog or the API connection prompt is waiting in Gateway/TWS. Accept it, or add `127.0.0.1` to Trusted IPs. |
| Error 326, client id already in use | Another script is connected with id 17. Pass `--client-id 18`. |
| Error 354 or 10167, market data not subscribed | The paper account has no market data. Share your live subscriptions with it (step 2) or subscribe to the US bundle. |
| Error 162, pacing violation | Too many historical requests. Wait ten minutes and rerun; cached symbols are skipped. |
| Error 200, no security definition | IBKR doesn't recognise the ticker (for example a recent rename). The symbol is skipped. |

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
