"""Tests for Clark Kent daily-post opp_id dedup (Step 7 hardening).

Covers the 2026-04-24 fix:

  - `generate_daily_posts()` now consumes each `opp_id` at most once across the
    four generators. Before Step 7, a single high-edge opp in a sparse pool
    could win every selector and be posted 4× on Binance Square, producing
    duplicate content and misleading "independent confirmation" signal.

  - Only opp-selecting generators tag their post with `opp_id`:
      * `_top_liquid_opportunity` — picks a single best opportunity.
      * `_zatanna_prediction` — picks max-edge opp as base.
    The other two (`_morning_alpha`, `_stablecoin_depth`) aggregate and MUST
    remain untagged so they never consume an opp_id spuriously.
"""

from unittest.mock import MagicMock, patch


def _make_generator():
    """Build a DailyPostGenerator with all external deps mocked.

    Patches both external-dep constructors at module level before instantiating,
    so __init__ doesn't hit ccxt / Ollama / the filesystem.
    """
    with (
        patch("clark_kent.daily_generator.Aquaman", return_value=MagicMock()),
        patch("clark_kent.daily_generator.ZatannaPredictor", return_value=MagicMock()),
    ):
        from clark_kent.daily_generator import DailyPostGenerator

        gen = DailyPostGenerator(dry_run=True)
    # generate_daily_posts calls self.aquaman.get_market_summary() — give it
    # something sensible so _stablecoin_depth can render.
    gen.aquaman.get_market_summary = MagicMock(
        return_value={
            "best_market": {
                "symbol": "BTC/USDT",
                "depth_usd": 50_000.0,
                "spread_pct": 0.01,
                "slippage_pct": 0.05,
            }
        }
    )
    return gen


def _p2p_opp(opp_id: str, edge: float, market: str = "MXN") -> dict:
    """Minimal P2P opportunity shape that survives the generator selectors."""
    return {
        "opp_id": opp_id,
        "scanner_id": "C-P2P-LATAM",
        "asset": "USDT",
        "market": market,
        "edge_net": edge,
        "merchant_count": 8,
        "depth_estimate": 20_000.0,
        "liquidity": {"depth_usd": 20_000.0, "slippage_pct": 0.1, "symbol": f"USDT/{market}"},
    }


def test_single_dominant_opp_is_posted_at_most_once(monkeypatch):
    """One opp_id winning multiple selectors must only tag one post."""
    gen = _make_generator()

    # Same opp_id, very high edge → would win both _top_liquid_opportunity and
    # _zatanna_prediction if dedup wasn't in place.
    dominant = _p2p_opp("OPP-DOMINANT-1", edge=5.0)
    monkeypatch.setattr(gen, "_filter_with_aquaman", lambda data: [dominant])
    monkeypatch.setattr(gen, "_load_recent_data", lambda: [dominant])

    posts = gen.generate_daily_posts()

    tagged_opp_ids = [p.get("opp_id") for p in posts if p.get("opp_id")]
    assert len(tagged_opp_ids) <= 1, (
        f"Expected at most 1 tagged post for a single dominant opp, " f"got {len(tagged_opp_ids)}: {tagged_opp_ids}"
    )
    # And whatever was tagged must be the dominant one.
    if tagged_opp_ids:
        assert tagged_opp_ids[0] == "OPP-DOMINANT-1"


def test_two_distinct_opps_tag_different_posts(monkeypatch):
    """Two high-edge opps → both tagging generators select different opp_ids."""
    gen = _make_generator()

    opp_a = _p2p_opp("OPP-A", edge=5.0, market="MXN")
    opp_b = _p2p_opp("OPP-B", edge=4.0, market="ARS")
    monkeypatch.setattr(gen, "_filter_with_aquaman", lambda data: [opp_a, opp_b])
    monkeypatch.setattr(gen, "_load_recent_data", lambda: [opp_a, opp_b])

    posts = gen.generate_daily_posts()

    tagged_opp_ids = [p.get("opp_id") for p in posts if p.get("opp_id")]
    # Both _top_liquid_opportunity and _zatanna_prediction should tag — and
    # dedup guarantees the two IDs are different.
    assert len(tagged_opp_ids) == 2, f"Expected 2 tagged posts, got {tagged_opp_ids}"
    assert len(set(tagged_opp_ids)) == 2, f"Tagged posts collided on opp_id: {tagged_opp_ids}"
    assert set(tagged_opp_ids) == {"OPP-A", "OPP-B"}


def test_empty_pool_produces_four_untagged_posts(monkeypatch):
    """An empty verified pool still emits 4 posts — none with opp_id."""
    gen = _make_generator()
    monkeypatch.setattr(gen, "_filter_with_aquaman", lambda data: [])
    monkeypatch.setattr(gen, "_load_recent_data", lambda: [])

    posts = gen.generate_daily_posts()

    assert len(posts) == 4
    assert all("opp_id" not in p for p in posts), (
        f"No post should carry opp_id when pool is empty: " f"{[p.get('opp_id') for p in posts]}"
    )


def test_aggregating_generators_never_tag(monkeypatch):
    """_morning_alpha and _stablecoin_depth must never carry opp_id.

    These generators aggregate across the pool; they don't select a single
    opportunity. Tagging them would spuriously consume an opp_id and starve
    the downstream opp-selecting generators.
    """
    gen = _make_generator()

    opp = _p2p_opp("OPP-AGG-1", edge=5.0)
    monkeypatch.setattr(gen, "_filter_with_aquaman", lambda data: [opp])
    monkeypatch.setattr(gen, "_load_recent_data", lambda: [opp])

    posts = gen.generate_daily_posts()

    morning = next(p for p in posts if p["type"] == "morning_alpha")
    stablecoin = next(p for p in posts if p["type"] == "stablecoin_depth")
    assert "opp_id" not in morning
    assert "opp_id" not in stablecoin


def test_build_post_without_opp_id_does_not_add_key():
    """_build_post keeps its historical shape when opp_id is not provided."""
    gen = _make_generator()
    post = gen._build_post("08:00 AM", "test_type", "$USDT hello #crypto")
    assert "opp_id" not in post
    assert post["time"] == "08:00 AM"
    assert post["type"] == "test_type"


def test_build_post_with_opp_id_adds_key():
    """_build_post attaches opp_id when caller provides one."""
    gen = _make_generator()
    post = gen._build_post("08:00 AM", "test_type", "$USDT hello #crypto", opp_id="OPP-X-123")
    assert post.get("opp_id") == "OPP-X-123"
