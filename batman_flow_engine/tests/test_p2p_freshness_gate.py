"""Tests for Step 9 P2P publish-time freshness gate.

Covers the 2026-04-24 fix:

  - `core.p2p_latam.ad_snapshot(fiat, asset)` returns a fresh Binance P2P
    merchant snapshot; caches non-empty results for ~60s, never caches
    empty / error snapshots.
  - `engine._p2p_freshness_gate_passes(opportunity)` gates Clark Kent
    publication of P2P opps: requires ≥3 BUY ads AND ≥3 SELL ads on the
    live order book AND <0.5% drift between the scanner's recorded
    p2p_buy_price and the current top-of-book BUY price.

Scanner verification (`_verify_p2p_opportunity`) can be minutes old by
publish time. The gate re-checks the market at the last possible moment
before we broadcast on Binance Square.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ──────────────────────────── fixtures ────────────────────────────


@pytest.fixture(autouse=True)
def _reset_ad_snapshot_cache():
    """Wipe the module-level snapshot cache before each test."""
    from core import p2p_latam

    with p2p_latam._AD_SNAPSHOT_CACHE_LOCK:
        p2p_latam._AD_SNAPSHOT_CACHE.clear()
    yield
    with p2p_latam._AD_SNAPSHOT_CACHE_LOCK:
        p2p_latam._AD_SNAPSHOT_CACHE.clear()


def _ad(price: float, amount: float = 5000.0) -> dict:
    return {
        "price": price,
        "available_amount": amount,
        "min_order_limit": 100.0,
        "max_order_limit": 10_000.0,
        "merchant_name": "m",
    }


# ─────────────── ad_snapshot cache + fetch semantics ───────────────


def test_ad_snapshot_caches_non_empty_within_ttl():
    """Two back-to-back calls must hit the cache (one BUY + one SELL fetch total)."""
    from core import p2p_latam

    with patch.object(p2p_latam, "get_p2p_announcements_binance") as fetch:
        # 5 BUY + 5 SELL on the first call, cached thereafter.
        fetch.side_effect = lambda fiat, crypto, trade_type, top_n: [
            _ad(18.10 if trade_type == "BUY" else 18.00) for _ in range(5)
        ]
        s1 = p2p_latam.ad_snapshot("MXN", "USDT")
        s2 = p2p_latam.ad_snapshot("MXN", "USDT")

    assert s1["buy_ads"] == 5 and s1["sell_ads"] == 5
    assert s2["buy_ads"] == 5 and s2["sell_ads"] == 5
    # First call = 1 BUY + 1 SELL. Second call served entirely from cache.
    assert fetch.call_count == 2


def test_ad_snapshot_does_not_cache_empty_buy():
    """An empty BUY side must NOT be cached — next call retries the API."""
    from core import p2p_latam

    with patch.object(p2p_latam, "get_p2p_announcements_binance") as fetch:
        fetch.side_effect = lambda fiat, crypto, trade_type, top_n: (
            [] if trade_type == "BUY" else [_ad(18.00) for _ in range(5)]
        )
        s1 = p2p_latam.ad_snapshot("MXN", "USDT")
        s2 = p2p_latam.ad_snapshot("MXN", "USDT")

    assert s1["buy_ads"] == 0 and s1["top_buy"] is None
    assert s2["buy_ads"] == 0
    # Two full round-trips = 4 fetches; cache never filled.
    assert fetch.call_count == 4


def test_ad_snapshot_cache_expires_past_ttl(monkeypatch):
    """Past _AD_SNAPSHOT_TTL_SEC the entry must be evicted and refetched."""
    from core import p2p_latam

    clock = [1_000.0]
    monkeypatch.setattr(p2p_latam, "monotonic", lambda: clock[0])

    with patch.object(p2p_latam, "get_p2p_announcements_binance") as fetch:
        fetch.side_effect = lambda fiat, crypto, trade_type, top_n: [
            _ad(18.10 if trade_type == "BUY" else 18.00) for _ in range(5)
        ]

        p2p_latam.ad_snapshot("MXN", "USDT")  # t=1000, caches
        clock[0] = 1_000.0 + p2p_latam._AD_SNAPSHOT_TTL_SEC + 1
        p2p_latam.ad_snapshot("MXN", "USDT")  # past TTL, refetches

    assert fetch.call_count == 4  # 2 per call × 2 calls


def test_ad_snapshot_shape_and_top_prices():
    """Snapshot dict carries the contract the engine gate expects."""
    from core import p2p_latam

    buy_prices = [18.10, 18.11, 18.12, 18.13, 18.14]
    sell_prices = [18.00, 17.99, 17.98, 17.97, 17.96]
    with patch.object(p2p_latam, "get_p2p_announcements_binance") as fetch:
        fetch.side_effect = lambda fiat, crypto, trade_type, top_n: [
            _ad(p) for p in (buy_prices if trade_type == "BUY" else sell_prices)
        ]
        snap = p2p_latam.ad_snapshot("MXN", "USDT")

    assert snap["fiat"] == "MXN"
    assert snap["asset"] == "USDT"
    assert snap["buy_ads"] == 5
    assert snap["sell_ads"] == 5
    assert snap["top_buy"] == 18.10
    assert snap["top_sell"] == 18.00
    assert isinstance(snap["fetched_at"], float)


# ──────────── engine._p2p_freshness_gate_passes semantics ────────────


def test_gate_passes_with_fresh_liquid_book():
    """≥3 BUY + ≥3 SELL ads AND drift <0.5% → True."""
    import engine

    with patch.object(engine, "_p2p_freshness_gate_passes", wraps=engine._p2p_freshness_gate_passes):
        with patch("core.p2p_latam.ad_snapshot") as snap_mock:
            snap_mock.return_value = {
                "fetched_at": 1.0,
                "fiat": "MXN",
                "asset": "USDT",
                "buy_ads": 5,
                "sell_ads": 5,
                "top_buy": 18.10,
                "top_sell": 18.00,
            }
            opp = {
                "opp_id": "OPP-OK",
                "scanner_id": "C-P2P-LATAM",
                "market": "MXN",
                "asset": "USDT",
                "p2p_buy_price": 18.08,  # 0.11% drift — within 0.5%
            }
            assert engine._p2p_freshness_gate_passes(opp) is True


def test_gate_fails_on_price_drift():
    """Top-of-book drifted >0.5% from scanner's recorded price → False."""
    import engine

    with patch("core.p2p_latam.ad_snapshot") as snap_mock:
        snap_mock.return_value = {
            "fetched_at": 1.0,
            "fiat": "MXN",
            "asset": "USDT",
            "buy_ads": 5,
            "sell_ads": 5,
            "top_buy": 18.50,
            "top_sell": 18.00,
        }
        opp = {
            "opp_id": "OPP-DRIFT",
            "scanner_id": "C-P2P-LATAM",
            "market": "MXN",
            "asset": "USDT",
            "p2p_buy_price": 18.08,  # ~2.3% drift
        }
        assert engine._p2p_freshness_gate_passes(opp) is False


def test_gate_fails_on_thin_book():
    """<3 BUY ads → False, regardless of price proximity."""
    import engine

    with patch("core.p2p_latam.ad_snapshot") as snap_mock:
        snap_mock.return_value = {
            "fetched_at": 1.0,
            "fiat": "MXN",
            "asset": "USDT",
            "buy_ads": 2,
            "sell_ads": 8,
            "top_buy": 18.10,
            "top_sell": 18.00,
        }
        opp = {
            "opp_id": "OPP-THIN",
            "scanner_id": "C-P2P-LATAM",
            "market": "MXN",
            "asset": "USDT",
            "p2p_buy_price": 18.08,
        }
        assert engine._p2p_freshness_gate_passes(opp) is False


def test_gate_fails_and_logs_on_missing_market(caplog):
    """No market → ERROR log + False. Engine must not silently publish."""
    import engine
    import logging

    opp = {
        "opp_id": "OPP-NOMARKET",
        "scanner_id": "C-P2P-LATAM",
        "asset": "USDT",
        "p2p_buy_price": 18.08,
    }
    with caplog.at_level(logging.ERROR, logger="engine"):
        assert engine._p2p_freshness_gate_passes(opp) is False
    assert any("missing market" in rec.getMessage() for rec in caplog.records)


def test_gate_fails_when_snapshot_raises(caplog):
    """Upstream fetch exception → ERROR log + False, does not crash engine."""
    import engine
    import logging

    with patch("core.p2p_latam.ad_snapshot", side_effect=RuntimeError("binance p2p down")):
        opp = {
            "opp_id": "OPP-EXC",
            "scanner_id": "C-P2P-LATAM",
            "market": "MXN",
            "asset": "USDT",
            "p2p_buy_price": 18.08,
        }
        with caplog.at_level(logging.ERROR, logger="engine"):
            assert engine._p2p_freshness_gate_passes(opp) is False
    assert any("fetch failed" in rec.getMessage() for rec in caplog.records)


def test_gate_fails_on_missing_top_buy():
    """Empty book (top_buy=None) → False even if ad counts somehow satisfy."""
    import engine

    with patch("core.p2p_latam.ad_snapshot") as snap_mock:
        # Pathological — shouldn't happen because ad_snapshot won't cache
        # empty snapshots, but if upstream returns this shape we must not pass.
        snap_mock.return_value = {
            "fetched_at": 1.0,
            "fiat": "MXN",
            "asset": "USDT",
            "buy_ads": 5,
            "sell_ads": 5,
            "top_buy": None,
            "top_sell": None,
        }
        opp = {
            "opp_id": "OPP-NOTOP",
            "scanner_id": "C-P2P-LATAM",
            "market": "MXN",
            "asset": "USDT",
            "p2p_buy_price": 18.08,
        }
        assert engine._p2p_freshness_gate_passes(opp) is False
