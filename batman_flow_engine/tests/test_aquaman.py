"""Tests for AQUAMAN liquidity cache + exchange inference (Step 4 hardening).

Covers the 2026-04-22 fixes:

  - Liquidity cache honours CACHE_TTL_SECONDS and does not serve stale entries.
  - Error results are NEVER cached — a transient upstream failure must not
    permanently poison the cache for that (exchange, symbol, amount).
  - `infer_exchange_id` returns None when the opportunity's metadata doesn't
    name a supported venue (no silent "binance" fallback).
  - `verify_opportunity` returns None when exchange can't be inferred.
  - OKX opportunities continue to return None (was a special case before,
    preserved).
"""

from unittest.mock import MagicMock, patch


def _make_aquaman_without_ccxt():
    """Build an Aquaman instance, then swap the ccxt clients for MagicMocks.

    We patch the ccxt constructors at Aquaman construction time so __init__
    doesn't hit the network. Then tests can stub `exchange.fetch_order_book`
    directly on the mock.
    """
    with (
        patch("core.aquaman.ccxt.binance", return_value=MagicMock()),
        patch("core.aquaman.ccxt.bybit", return_value=MagicMock()),
        patch("core.aquaman.ccxt.bitget", return_value=MagicMock()),
    ):
        from core.aquaman import Aquaman

        return Aquaman()


def _liquid_order_book() -> dict:
    """A rich order book that comfortably clears MIN_DEPTH_USD and slippage."""
    # 200 levels of depth @ 1 unit each, spaced tightly. Plenty of liquidity.
    bids = [[100.0 - i * 0.001, 100.0] for i in range(200)]
    asks = [[100.0 + i * 0.001, 100.0] for i in range(200)]
    return {"bids": bids, "asks": asks}


def test_cache_hit_within_ttl_avoids_refetch():
    """A second call within TTL must NOT re-hit fetch_order_book."""
    aq = _make_aquaman_without_ccxt()
    aq.exchanges["binance"].fetch_order_book.return_value = _liquid_order_book()

    r1 = aq.check_liquidity("binance", "BTC/USDT", amount_usd=100.0)
    r2 = aq.check_liquidity("binance", "BTC/USDT", amount_usd=100.0)

    assert r1["status"] == "ok"
    assert r2["status"] == "ok"
    assert aq.exchanges["binance"].fetch_order_book.call_count == 1


def test_cache_entry_expires_after_ttl_elapses():
    """Past CACHE_TTL_SECONDS, the cache must drop the entry and refetch."""
    aq = _make_aquaman_without_ccxt()
    aq.exchanges["binance"].fetch_order_book.return_value = _liquid_order_book()

    from core.aquaman import CACHE_TTL_SECONDS

    # First call caches at t=1000.
    with patch("core.aquaman.time.monotonic", return_value=1000.0):
        aq.check_liquidity("binance", "BTC/USDT", amount_usd=100.0)
    assert aq.exchanges["binance"].fetch_order_book.call_count == 1

    # Second call one second past TTL — must evict and refetch.
    with patch("core.aquaman.time.monotonic", return_value=1000.0 + CACHE_TTL_SECONDS + 1):
        aq.check_liquidity("binance", "BTC/USDT", amount_usd=100.0)
    assert aq.exchanges["binance"].fetch_order_book.call_count == 2


def test_error_results_are_not_cached():
    """A transient upstream error must NOT poison the cache."""
    aq = _make_aquaman_without_ccxt()
    # First call raises, second call succeeds. If the error were cached,
    # the second call would short-circuit and fetch_order_book would only
    # be called once.
    aq.exchanges["binance"].fetch_order_book.side_effect = [
        RuntimeError("temporary exchange hiccup"),
        _liquid_order_book(),
    ]

    r1 = aq.check_liquidity("binance", "BTC/USDT", amount_usd=100.0)
    assert r1["status"] == "error"

    r2 = aq.check_liquidity("binance", "BTC/USDT", amount_usd=100.0)
    assert r2["status"] == "ok"
    assert aq.exchanges["binance"].fetch_order_book.call_count == 2


def test_infer_exchange_returns_none_for_unknown_venue():
    """Unknown venues must return None, not a silent binance fallback."""
    aq = _make_aquaman_without_ccxt()
    # Scanner_id / venue fields that don't contain binance/bybit/bitget.
    opp = {"opp_id": "OPP-X", "scanner_id": "A-CROSS-EXCHANGE", "venue": "bitso"}
    assert aq.infer_exchange_id(opp) is None


def test_infer_exchange_returns_none_for_okx():
    """OKX opportunities still return None (we don't have an OKX ccxt client)."""
    aq = _make_aquaman_without_ccxt()
    opp = {"opp_id": "OPP-OKX", "scanner_id": "D-MULTI-EXCHANGE", "venue": "okx"}
    assert aq.infer_exchange_id(opp) is None


def test_verify_opportunity_returns_none_when_exchange_unknown():
    """End-to-end: unknown exchange → verify_opportunity short-circuits to None."""
    aq = _make_aquaman_without_ccxt()
    opp = {
        "opp_id": "OPP-UNKNOWN",
        "scanner_id": "D-MULTI-EXCHANGE",
        "venue": "bitso",
        "asset": "BTC",
        "market": "USD",
    }
    assert aq.verify_opportunity(opp) is None
    # And since we bailed on infer_exchange_id, fetch_order_book must NOT run.
    assert aq.exchanges["binance"].fetch_order_book.call_count == 0
