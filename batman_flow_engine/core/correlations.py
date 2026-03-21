from __future__ import annotations
import pandas as pd
import numpy as np


# ─────────────────────────────────────────────
# 1) CORRELATION STRESS (GENERAL)
# ─────────────────────────────────────────────
def rolling_corr_stress(returns: pd.DataFrame, window: int = 60) -> dict:
    """
    Stress proxy: average of absolute pairwise correlations over a rolling window.
    When correlations spike, diversification collapses and systemic fragility rises.
    """
    if returns is None or returns.empty or len(returns) < window + 5:
        return {"status": "no_data", "corr_stress": 0.0}

    r = returns.tail(window).dropna(axis=1, how="any")
    if r.shape[1] < 3:
        return {"status": "too_few_assets", "corr_stress": 0.0}

    corr = r.corr().abs()
    n = corr.shape[0]
    off = corr.values[np.triu_indices(n, k=1)]

    return {
        "status": "ok",
        "corr_stress": float(off.mean()),
        "n_assets": int(r.shape[1]),
        "window": int(window),
    }


# ─────────────────────────────────────────────
# 2) TOP CORRELATED EDGES (GENERAL)
# ─────────────────────────────────────────────
def top_corr_edges(returns: pd.DataFrame, window: int = 60, k: int = 20) -> pd.DataFrame:
    if returns is None or returns.empty or len(returns) < window + 5:
        return pd.DataFrame()

    r = returns.tail(window).dropna(axis=1, how="any")
    if r.shape[1] < 3:
        return pd.DataFrame()

    corr = r.corr()
    edges = []
    cols = list(corr.columns)

    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            edges.append((cols[i], cols[j], float(corr.iloc[i, j])))

    df = pd.DataFrame(edges, columns=["a", "b", "corr"])
    return df.sort_values("corr", ascending=False).head(k)


# ─────────────────────────────────────────────
# 3) VOLATILITY SHOCK SUMMARY
# ─────────────────────────────────────────────
def vol_shock_summary(vol_z_dict: dict) -> dict:
    """
    Aggregate volatility shock across universe.
    Expects {symbol: vol_z}
    """
    if not vol_z_dict:
        return {"status": "no_data"}

    values = [v for v in vol_z_dict.values() if isinstance(v, (int, float))]
    if not values:
        return {"status": "no_valid_values"}

    arr = np.array(values)

    return {
        "status": "ok",
        "mean_vol_z": float(arr.mean()),
        "pct_gt_2": float((arr > 2).mean()),
        "pct_gt_3": float((arr > 3).mean()),
        "max_vol_z": float(arr.max()),
        "n_assets": int(len(arr)),
    }


# ─────────────────────────────────────────────
# 4) DOWNSIDE CORRELATION (CRASH LAYER)
# ─────────────────────────────────────────────
def downside_corr_mean(returns: pd.DataFrame, benchmark: str = "SPY", window: int = 60, q: float = 0.2) -> dict:
    """
    Mean ABS pairwise correlations ONLY on benchmark bad days.
    Captures contagion during crashes better than full-sample corr.
    """
    base = {"benchmark": benchmark, "q": q, "window": window}

    try:
        r = returns.tail(window).dropna(axis=1, how="any")

        if benchmark not in r.columns:
            return {**base, "status": "error", "downside_corr_mean": None, "tail_points": 0}

        b = r[benchmark]
        threshold = b.quantile(q)
        mask = b <= threshold
        rr = r[mask]

        if len(rr) < 5:
            return {**base, "status": "insufficient_tail_data", "downside_corr_mean": None, "tail_points": int(len(rr))}

        corr = rr.corr().abs()
        n = corr.shape[0]
        off = corr.values[np.triu_indices(n, k=1)]

        if len(off) == 0:
            return {**base, "status": "no_valid_pairs", "downside_corr_mean": None, "tail_points": int(len(rr))}

        return {
            "status": "ok",
            "downside_corr_mean": float(off.mean()),
            "tail_points": int(len(rr)),
            "benchmark": benchmark,
            "q": q,
            "window": window,
        }

    except Exception as e:
        return {**base, "status": "error", "error": str(e), "downside_corr_mean": None, "tail_points": 0}


# ─────────────────────────────────────────────
# 5) TOP DOWNSIDE EDGES
# ─────────────────────────────────────────────
def top_downside_edges(
    returns: pd.DataFrame, benchmark: str = "SPY", window: int = 60, q: float = 0.2, k: int = 20
) -> pd.DataFrame:
    empty = pd.DataFrame(columns=["a", "b", "corr"])

    try:
        r = returns.tail(window).dropna(axis=1, how="any")

        if benchmark not in r.columns:
            return empty

        b = r[benchmark]
        threshold = b.quantile(q)
        mask = b <= threshold
        rr = r[mask]

        if len(rr) < 5:
            return empty

        corr = rr.corr()
        edges = []
        cols = list(corr.columns)

        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                val = corr.iloc[i, j]
                if pd.notna(val):
                    edges.append({"a": cols[i], "b": cols[j], "corr": float(val)})

        if not edges:
            return empty

        df = pd.DataFrame(edges)
        df["_abs"] = df["corr"].abs()
        df = df.sort_values("_abs", ascending=False).head(k)
        return df.drop(columns=["_abs"]).reset_index(drop=True)

    except Exception:
        return empty
