from __future__ import annotations
import numpy as np
import pandas as pd


def normalize_weights(weights: dict) -> dict:
    w = {k: float(v) for k, v in weights.items() if v is not None}
    s = sum(w.values())
    if s <= 0:
        return {}
    return {k: v / s for k, v in w.items()}


def projection_from_returns(returns: pd.Series, horizon_days: int) -> dict:
    """
    Simple normal approximation using historical daily returns:
      mu_h = mu * horizon
      sigma_h = sigma * sqrt(horizon)
    Returns p5, p50, p95 for horizon return.
    """
    r = returns.dropna()
    if r.empty or r.std() == 0:
        return {"p5": 0.0, "p50": 0.0, "p95": 0.0, "mu": 0.0, "sigma": 0.0}
    mu = float(r.mean())
    sigma = float(r.std())
    mu_h = mu * horizon_days
    sigma_h = sigma * np.sqrt(horizon_days)
    # percentiles of N(mu_h, sigma_h)
    p5 = mu_h + (-1.64485) * sigma_h
    p50 = mu_h
    p95 = mu_h + (1.64485) * sigma_h
    return {"p5": p5, "p50": p50, "p95": p95, "mu": mu_h, "sigma": sigma_h}


def portfolio_projection(returns_df: pd.DataFrame, weights: dict) -> dict:
    """
    Builds portfolio daily return series: r_p = sum_i w_i r_i
    and computes projections for 1D, 5D, 22D horizons.
    """
    w = normalize_weights(weights)
    if not w or returns_df is None or returns_df.empty:
        return {"status": "no_data"}
    # align
    cols = [c for c in returns_df.columns if c in w]
    if len(cols) < 2:
        return {"status": "too_few_assets"}
    r = returns_df[cols].replace([np.inf, -np.inf], np.nan).dropna()
    if r.empty:
        return {"status": "no_overlap"}
    wv = np.array([w[c] for c in cols])
    wv = wv / wv.sum()
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        rp = r.values @ wv
    rp = pd.Series(rp, index=r.index, name="port_ret")
    return {
        "status": "ok",
        "horizons": {
            "1D": projection_from_returns(rp, 1),
            "1W": projection_from_returns(rp, 5),
            "1M": projection_from_returns(rp, 22),
        },
    }
