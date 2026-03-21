from __future__ import annotations
import math
import time
import hashlib
from typing import Any

import numpy as np
import pandas as pd


def zscore(series: pd.Series, window: int) -> pd.Series:
    m = series.rolling(window).mean()
    s = series.rolling(window).std()
    return (series - m) / s


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (float, int)):
            return float(x)
        if isinstance(x, (np.floating, np.integer)):
            return float(x)
        return float(x)
    except Exception:
        return default


def annualize_vol(std: float, periods_per_year: float) -> float:
    return float(std * math.sqrt(periods_per_year))


def now_ts() -> int:
    return int(time.time())


def hash_key(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
