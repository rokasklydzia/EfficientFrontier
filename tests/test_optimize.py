import numpy as np
import pandas as pd
import pytest

from frontier.data import clean_prices, estimate_moments, load_prices, periods_per_year
from frontier.optimize import efficient_frontier, max_return, min_variance, tangency


@pytest.fixture
def moments():
    prices, _, _ = load_prices()
    return estimate_moments(clean_prices(prices))


def test_weights_are_long_only_and_sum_to_one(moments):
    for p in efficient_frontier(moments.mu, moments.cov, max_weight=0.3, points=15):
        assert p.weights.sum() == pytest.approx(1, abs=1e-6)
        assert (p.weights >= -1e-8).all()
        assert (p.weights <= 0.3 + 1e-6).all()


def test_frontier_is_increasing_in_risk_and_return(moments):
    frontier = efficient_frontier(moments.mu, moments.cov, points=20)
    rets = np.array([p.ret for p in frontier])
    vols = np.array([p.vol for p in frontier])
    assert np.all(np.diff(rets) > -1e-6)
    assert np.all(np.diff(vols) > -1e-6)


def test_no_asset_beats_the_frontier(moments):
    frontier = efficient_frontier(moments.mu, moments.cov, points=60)
    vols = np.array([p.vol for p in frontier])
    rets = np.array([p.ret for p in frontier])
    for sym in moments.mu.index:
        vol = np.sqrt(moments.cov.loc[sym, sym])
        ret = moments.mu[sym]
        # Frontier return at that volatility (or the top of the frontier if the asset is riskier).
        frontier_ret = np.interp(vol, vols, rets)
        assert ret <= frontier_ret + 2e-3, sym


def test_min_variance_beats_every_asset(moments):
    gmv = min_variance(moments.mu, moments.cov)
    assert gmv.vol <= np.sqrt(np.diag(moments.cov.values)).min() + 1e-8


def test_tangency_has_highest_sharpe(moments):
    rf = 0.03
    tan = tangency(moments.mu, moments.cov, rf)
    for p in efficient_frontier(moments.mu, moments.cov, rf=rf, points=40):
        assert p.sharpe <= tan.sharpe + 1e-4


def test_tangency_matches_closed_form_when_unconstrained():
    # With all-positive closed-form weights, long-only constraints don't bind, so w ~ inv(S)(mu - rf).
    mu = pd.Series([0.08, 0.10, 0.12], index=list("abc"))
    vols = np.array([0.15, 0.18, 0.22])
    corr = np.array([[1, 0.2, 0.1], [0.2, 1, 0.3], [0.1, 0.3, 1]])
    cov = pd.DataFrame(np.outer(vols, vols) * corr, index=mu.index, columns=mu.index)
    raw = np.linalg.solve(cov.values, mu.values - 0.02)
    expected = raw / raw.sum()
    assert (expected > 0).all()
    np.testing.assert_allclose(tangency(mu, cov, 0.02).weights.values, expected, atol=1e-4)


def test_max_return_respects_cap():
    mu = pd.Series([0.2, 0.1, 0.05], index=list("abc"))
    assert max_return(mu, 1.0) == pytest.approx(0.2)
    assert max_return(mu, 0.5) == pytest.approx(0.15)


def test_infeasible_cap_raises(moments):
    with pytest.raises(ValueError):
        min_variance(moments.mu, moments.cov, max_weight=0.01)


def test_periods_per_year():
    assert periods_per_year(pd.bdate_range("2024-01-01", periods=50)) == 252
    assert periods_per_year(pd.date_range("2024-01-01", periods=50, freq="W")) == 52
    assert periods_per_year(pd.date_range("2024-01-01", periods=50, freq="ME")) == 12


def test_clean_prices_drops_short_history_and_fills_gaps():
    idx = pd.bdate_range("2024-01-01", periods=100)
    prices = pd.DataFrame({"full": np.linspace(100, 110, 100), "short": np.nan, "gappy": np.linspace(50, 60, 100)},
                          index=idx)
    prices.iloc[80:, 1] = 1.0
    prices.iloc[10:12, 2] = np.nan
    out = clean_prices(prices, min_coverage=0.9)
    assert list(out.columns) == ["full", "gappy"]
    assert len(out) == 100
