from __future__ import annotations

import threading
import numpy as np
import pandas as pd
import yfinance as yf

from .utils import zscore, safe_float, annualize_vol

# yfinance puede volverse inestable con concurrencia; lo serializamos.
_YF_LOCK = threading.Lock()


def _close_series(df: pd.DataFrame) -> pd.Series:
    """
    yfinance a veces devuelve 'Close' como DataFrame (multi-col) incluso para 1 ticker,
    especialmente bajo concurrencia. Aquí lo normalizamos a Series.
    """
    c = df["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    return c


def fetch_equity_daily(ticker: str, days: str = "180d") -> pd.DataFrame:
    with _YF_LOCK:
        d = yf.download(
            ticker,
            period=days,
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=False,
        )
    if d is None or d.empty:
        return pd.DataFrame()

    close = _close_series(d)
    # evita warning pandas fill_method
    import numpy as np

    d["ret1d"] = np.log(close / close.shift(1))
    return d


def fetch_equity_intraday(ticker: str, period: str = "7d", interval: str = "5m") -> pd.DataFrame:
    with _YF_LOCK:
        i = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=False,
        )
    if isinstance(i.columns, pd.MultiIndex):
        i.columns = i.columns.get_level_values(0)
    if i is None or i.empty:
        return pd.DataFrame()

    close = _close_series(i)
    i["ret"] = np.log(close / close.shift(1))
    return i


def equity_metrics(ticker: str, vol_z_window: int = 20, rvol_window: int = 20) -> dict:
    d = fetch_equity_daily(ticker, "240d")
    if d.empty or len(d) < (vol_z_window + 5):
        return {"symbol": ticker, "status": "no_daily"}

    # realized vol proxy (annualized, daily)
    rv20_ann = annualize_vol(d["ret1d"].rolling(20).std().iloc[-1], 252)

    # use intraday if possible for near-term anomaly; fallback to daily volume
    i = fetch_equity_intraday(ticker, "7d", "5m")
    if not i.empty and len(i) > (vol_z_window + 10):
        i["Close"] = _close_series(i)
        i["vol_z"] = zscore(i["Volume"], vol_z_window)
        i["rvol"] = i["Volume"] / i["Volume"].rolling(rvol_window).mean()

        latest = i.iloc[-1]
        dollar_vol = safe_float(latest["Close"]) * safe_float(latest["Volume"])
        ret_intra = safe_float(i["Close"].iloc[-1] / i["Close"].iloc[0] - 1.0)

        return {
            "symbol": ticker,
            "px": safe_float(latest["Close"]),
            "ret_1d": safe_float(d["ret1d"].iloc[-1]),
            "ret_intra": ret_intra,
            "vol_z": safe_float(latest["vol_z"]),
            "rvol": safe_float(latest["rvol"]),
            "dollar_vol": safe_float(dollar_vol),
            "rv20_ann": safe_float(rv20_ann),
            "status": "ok",
        }

    # daily fallback
    d["vol_z"] = zscore(d["Volume"], vol_z_window)
    d["rvol"] = d["Volume"] / d["Volume"].rolling(rvol_window).mean()

    latest = d.iloc[-1]
    dollar_vol = safe_float(latest["Close"]) * safe_float(latest["Volume"])

    return {
        "symbol": ticker,
        "px": safe_float(latest["Close"]),
        "ret_1d": safe_float(latest["ret1d"]),
        "ret_intra": 0.0,
        "vol_z": safe_float(latest["vol_z"]),
        "rvol": safe_float(latest["rvol"]),
        "dollar_vol": safe_float(dollar_vol),
        "rv20_ann": safe_float(rv20_ann),
        "status": "ok_daily",
    }


def returns_matrix(tickers: list[str], days: str = "240d") -> pd.DataFrame:
    # Para matrices multi-ticker es normal MultiIndex; aquí lo manejamos correctamente.
    with _YF_LOCK:
        d = yf.download(
            tickers,
            period=days,
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="column",
            threads=False,
        )
    if d is None or d.empty:
        return pd.DataFrame()

    if isinstance(d.columns, pd.MultiIndex):
        px = d["Close"]
        # si por alguna razón Close sigue siendo DF raro, normalizamos columnas
        if isinstance(px, pd.DataFrame):
            pass
    else:
        px = d[["Close"]]

    rets = np.log(px / px.shift(1)).dropna(how="all")
    return rets.dropna(axis=1, how="all")
