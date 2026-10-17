"""Long-only Markowitz mean-variance optimisation with an optional per-asset weight cap."""

from __future__ import annotations

from dataclasses import dataclass

import cvxpy as cp
import numpy as np
import pandas as pd


@dataclass
class Portfolio:
    weights: pd.Series
    ret: float
    vol: float
    sharpe: float


def _portfolio(w: np.ndarray, mu: pd.Series, cov: pd.DataFrame, rf: float) -> Portfolio:
    w = np.clip(w, 0, None)
    w = w / w.sum()
    ret = float(mu.values @ w)
    vol = float(np.sqrt(w @ cov.values @ w))
    return Portfolio(pd.Series(w, index=mu.index), ret, vol, (ret - rf) / vol if vol > 0 else np.nan)


def _solve(problem: cp.Problem) -> None:
    for solver in (cp.CLARABEL, cp.OSQP, cp.SCS):
        try:
            problem.solve(solver=solver)
            if problem.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
                return
        except cp.SolverError:
            continue
    raise RuntimeError(f"Optimisation failed with status {problem.status}")


def _check_cap(n: int, max_weight: float) -> None:
    if max_weight * n < 1 - 1e-9:
        raise ValueError(f"A max weight of {max_weight:.1%} across {n} assets cannot sum to 100%.")


def _sigma(cov: pd.DataFrame):
    # Symmetrise to remove floating-point asymmetry before handing the matrix to cvxpy.
    return cp.psd_wrap((cov.values + cov.values.T) / 2)


def min_variance(mu: pd.Series, cov: pd.DataFrame, max_weight: float = 1.0, rf: float = 0.0,
                 target_return: float | None = None) -> Portfolio:
    n = len(mu)
    _check_cap(n, max_weight)
    w = cp.Variable(n)
    constraints = [cp.sum(w) == 1, w >= 0, w <= max_weight]
    if target_return is not None:
        constraints.append(mu.values @ w >= target_return)
    _solve(cp.Problem(cp.Minimize(cp.quad_form(w, _sigma(cov))), constraints))
    return _portfolio(w.value, mu, cov, rf)


def max_return(mu: pd.Series, max_weight: float = 1.0) -> float:
    """Highest expected return reachable under the weight constraints (fill the top assets up to the cap)."""
    _check_cap(len(mu), max_weight)
    remaining, total = 1.0, 0.0
    for r in mu.sort_values(ascending=False):
        take = min(max_weight, remaining)
        total += take * r
        remaining -= take
        if remaining <= 1e-12:
            break
    return total


def tangency(mu: pd.Series, cov: pd.DataFrame, rf: float, max_weight: float = 1.0) -> Portfolio:
    """Maximum Sharpe ratio portfolio, via the standard homogenisation y = kappa * w."""
    n = len(mu)
    _check_cap(n, max_weight)
    excess = mu.values - rf
    if excess.max() <= 0:
        raise ValueError("No asset has an expected return above the risk-free rate, so there is no tangency portfolio.")
    y = cp.Variable(n)
    kappa = cp.Variable()
    constraints = [excess @ y == 1, y >= 0, cp.sum(y) == kappa, y <= max_weight * kappa, kappa >= 0]
    _solve(cp.Problem(cp.Minimize(cp.quad_form(y, _sigma(cov))), constraints))
    return _portfolio(y.value / kappa.value, mu, cov, rf)


def efficient_frontier(mu: pd.Series, cov: pd.DataFrame, max_weight: float = 1.0, rf: float = 0.0,
                       points: int = 40) -> list[Portfolio]:
    """Minimum-variance portfolios for evenly spaced target returns from the global minimum to the maximum."""
    gmv = min_variance(mu, cov, max_weight, rf)
    top = max_return(mu, max_weight)
    frontier = [gmv]
    for target in np.linspace(gmv.ret, top, points)[1:]:
        try:
            frontier.append(min_variance(mu, cov, max_weight, rf, target_return=target))
        except RuntimeError:
            break
    return frontier
