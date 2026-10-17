"""Streamlit app: long-only Markowitz efficient frontier across stocks, bonds and commodities.

    streamlit run app.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontier.data import clean_prices, estimate_moments, latest_tbill_rate, load_prices
from frontier.optimize import efficient_frontier, min_variance, tangency

st.set_page_config(page_title="Efficient Frontier", layout="wide")

CLASS_COLOURS = {"Equity": "#4C78A8", "Bond": "#54A24B", "Commodity": "#E45756", "Unknown": "#9D9D9D"}


@st.cache_data(show_spinner=False)
def cached_prices():
    return load_prices()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cached_tbill():
    return latest_tbill_rate()


@st.cache_data(show_spinner="Solving the frontier...")
def solve(prices: pd.DataFrame, rf: float, max_weight: float, points: int):
    m = estimate_moments(prices)
    frontier = efficient_frontier(m.mu, m.cov, max_weight, rf, points)
    gmv = min_variance(m.mu, m.cov, max_weight, rf)
    try:
        tan = tangency(m.mu, m.cov, rf, max_weight)
    except ValueError:
        tan = None
    return m, frontier, gmv, tan


prices_all, meta, source = cached_prices()
meta = meta.set_index("symbol")

st.title("Efficient frontier")
st.caption(f"Data: {source}. Long-only Markowitz on historical mean returns and sample covariance.")

with st.sidebar:
    st.header("Universe")
    classes = sorted(meta.loc[meta.index.intersection(prices_all.columns), "asset_class"].unique())
    chosen_classes = st.multiselect("Asset classes", classes, default=classes)

    first, last = prices_all.index.min().date(), prices_all.index.max().date()
    start, end = st.slider("Date window", min_value=first, max_value=last, value=(first, last), format="YYYY-MM")
    min_coverage = st.slider("Minimum history coverage", 0.5, 1.0, 0.95, 0.05,
                             help="Assets with less price history than this share of the window are dropped.")

    st.header("Optimisation")
    tbill = cached_tbill()
    rf = st.number_input("Risk-free rate (%)", value=round((tbill if tbill is not None else 0.04) * 100, 2),
                         step=0.25, help="Defaults to the latest 3-month T-bill yield from FRED.") / 100
    max_weight = st.slider("Max weight per asset (%)", 1, 100, 100) / 100
    points = st.slider("Frontier points", 10, 100, 40)

    st.header("Data")
    if st.button("Refresh from IBKR", help="Needs TWS or IB Gateway running on this machine."):
        from frontier.ibkr_fetch import fetch_all

        bar = st.progress(0.0)
        try:
            fetch_all(progress=lambda i, n, s: bar.progress(i / n, text=f"{s} ({i}/{n})"))
            cached_prices.clear()
            st.rerun()
        except Exception as exc:
            st.error(f"IBKR download failed: {exc}")

symbols = [s for s in prices_all.columns if meta["asset_class"].get(s, "Unknown") in chosen_classes]
window = prices_all.loc[str(start):str(end), symbols]
prices = clean_prices(window, min_coverage=min_coverage)
dropped = sorted(set(symbols) - set(prices.columns))

if prices.shape[1] < 2 or len(prices) < 3:
    st.warning("Not enough assets or dates in this selection. Widen the window or add asset classes.")
    st.stop()
if max_weight * prices.shape[1] < 1:
    st.warning(f"A {max_weight:.0%} cap across {prices.shape[1]} assets can't add up to 100%. Raise the cap.")
    st.stop()

m, frontier, gmv, tan = solve(prices, rf, max_weight, points)

n_obs = len(m.returns)
cols = st.columns(4)
cols[0].metric("Assets", prices.shape[1])
cols[1].metric("Observations", f"{n_obs}")
cols[2].metric("Window", f"{prices.index[0]:%Y-%m} to {prices.index[-1]:%Y-%m}")
cols[3].metric("Risk-free", f"{rf:.2%}")
if n_obs <= prices.shape[1]:
    st.warning(f"There are fewer observations ({n_obs}) than assets ({prices.shape[1]}), so the sample covariance "
               "is singular and the weights are very unreliable. Use daily data or fewer assets.")
if dropped:
    st.caption(f"Dropped for short history: {', '.join(dropped)}")

# Chart
asset_vol = np.sqrt(np.diag(m.cov.values))
asset_class = [meta["asset_class"].get(s, "Unknown") for s in m.mu.index]
fig = go.Figure()
for cls in dict.fromkeys(asset_class):
    idx = [i for i, c in enumerate(asset_class) if c == cls]
    fig.add_trace(go.Scatter(
        x=asset_vol[idx], y=m.mu.values[idx], mode="markers", name=cls,
        marker=dict(size=7, color=CLASS_COLOURS.get(cls, "#9D9D9D"), opacity=0.7),
        text=[m.mu.index[i] for i in idx],
        hovertemplate="%{text}<br>vol %{x:.1%}<br>return %{y:.1%}<extra></extra>",
    ))
fig.add_trace(go.Scatter(
    x=[p.vol for p in frontier], y=[p.ret for p in frontier], mode="lines", name="Efficient frontier",
    line=dict(color="#222", width=3), hovertemplate="vol %{x:.1%}<br>return %{y:.1%}<extra></extra>",
))
fig.add_trace(go.Scatter(x=[gmv.vol], y=[gmv.ret], mode="markers", name="Minimum variance",
                         marker=dict(symbol="diamond", size=14, color="#F58518", line=dict(color="#222", width=1))))
if tan is not None:
    x_max = max(asset_vol.max(), frontier[-1].vol) * 1.05
    fig.add_trace(go.Scatter(x=[0, x_max], y=[rf, rf + tan.sharpe * x_max], mode="lines", name="Capital market line",
                             line=dict(color="#B279A2", dash="dash")))
    fig.add_trace(go.Scatter(x=[tan.vol], y=[tan.ret], mode="markers", name="Tangency (max Sharpe)",
                             marker=dict(symbol="star", size=18, color="#B279A2", line=dict(color="#222", width=1))))
fig.update_layout(height=600, xaxis_title="Annualised volatility", yaxis_title="Annualised expected return",
                  xaxis_tickformat=".0%", yaxis_tickformat=".0%", legend=dict(orientation="h", y=-0.15),
                  margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig, width="stretch")


def weights_table(p) -> pd.DataFrame:
    w = p.weights[p.weights > 1e-4].sort_values(ascending=False)
    return pd.DataFrame({
        "Weight": w,
        "Name": [meta["name"].get(s, s) for s in w.index],
        "Class": [meta["asset_class"].get(s, "") for s in w.index],
    })


def class_split(p) -> str:
    split = p.weights.groupby(lambda s: meta["asset_class"].get(s, "Unknown")).sum()
    return ", ".join(f"{c} {v:.0%}" for c, v in split.sort_values(ascending=False).items() if v > 0.005)


left, right = st.columns(2)
for col, title, p in ((left, "Tangency portfolio", tan), (right, "Minimum variance portfolio", gmv)):
    with col:
        st.subheader(title)
        if p is None:
            st.info("No asset beats the risk-free rate in this window, so there is no tangency portfolio.")
            continue
        st.markdown(f"Return **{p.ret:.2%}**, volatility **{p.vol:.2%}**, Sharpe **{p.sharpe:.2f}**  \n{class_split(p)}")
        st.dataframe(weights_table(p).style.format({"Weight": "{:.2%}"}), width="stretch")

with st.expander("Pick a point on the frontier"):
    i = st.slider("Frontier point (low risk to high risk)", 0, len(frontier) - 1, len(frontier) // 2)
    p = frontier[i]
    st.markdown(f"Return **{p.ret:.2%}**, volatility **{p.vol:.2%}**, Sharpe **{p.sharpe:.2f}**  \n{class_split(p)}")
    st.dataframe(weights_table(p).style.format({"Weight": "{:.2%}"}), width="stretch")

with st.expander("Asset statistics"):
    stats = pd.DataFrame({"Return": m.mu, "Volatility": asset_vol, "Sharpe": (m.mu - rf) / asset_vol},
                         index=m.mu.index)
    stats.insert(0, "Class", asset_class)
    st.dataframe(stats.sort_values("Sharpe", ascending=False)
                 .style.format({"Return": "{:.2%}", "Volatility": "{:.2%}", "Sharpe": "{:.2f}"}),
                 width="stretch")
