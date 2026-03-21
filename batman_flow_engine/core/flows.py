from __future__ import annotations
import numpy as np


def flow_score_equity(vol_z: float, rvol: float, rv20_ann: float, dollar_vol: float) -> float:
    # vol_z (anomaly), rvol (relative volume), rv (stress), dollar_vol (liquidity proxy)
    liq = np.log10(max(dollar_vol, 1.0))
    return float((1.2 * vol_z) + (0.6 * (rvol - 1.0)) + (0.8 * rv20_ann) + (0.15 * liq))


def flow_score_crypto(spread: float, depth: float, rv_ann: float, dollar_vol_1h: float) -> float:
    # spread penalizes; depth/liquidity + vol/activity reward
    liq = np.log10(max(depth, 1.0))
    dv = np.log10(max(dollar_vol_1h, 1.0))
    return float((0.8 * rv_ann) + (0.35 * liq) + (0.15 * dv) - (50.0 * spread))
