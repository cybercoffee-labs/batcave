from __future__ import annotations
import pandas as pd
import ccxt

from .utils import safe_float, annualize_vol


def _get_exchange():
    return ccxt.binance({"enableRateLimit": True})


def crypto_metrics(symbol: str, lookback: int = 240, timeframe: str = "1h") -> dict:
    ex = _get_exchange()
    ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=lookback)
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    if df.empty or len(df) < 50:
        return {"symbol": symbol, "status": "no_ohlcv"}

    df["ret"] = df["close"].pct_change()
    # hourly -> annualize roughly: 24*365 periods
    rv = annualize_vol(df["ret"].rolling(48).std().iloc[-1], 24 * 365)

    ob = ex.fetch_order_book(symbol, limit=50)
    bids = ob.get("bids", [])
    asks = ob.get("asks", [])
    if not bids or not asks:
        return {"symbol": symbol, "status": "no_orderbook"}

    best_bid, best_ask = bids[0][0], asks[0][0]
    mid = (best_bid + best_ask) / 2
    spread = (best_ask - best_bid) / mid

    band = 0.005  # +/- 0.5%
    bid_depth = sum(q for p, q in bids if p >= mid * (1 - band))
    ask_depth = sum(q for p, q in asks if p <= mid * (1 + band))
    depth = bid_depth + ask_depth

    latest = df.iloc[-1]
    dollar_vol = safe_float(latest["close"]) * safe_float(latest["volume"])

    return {
        "symbol": symbol,
        "px": safe_float(latest["close"]),
        "ret_1h": safe_float(latest["ret"]),
        "rv_ann": safe_float(rv),
        "spread": safe_float(spread),
        "depth_0_5pct": safe_float(depth),
        "dollar_vol_1h": safe_float(dollar_vol),
        "status": "ok",
    }
