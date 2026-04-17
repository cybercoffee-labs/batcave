"""Tests for professional Clark Kent content generation."""

import json

from clark_kent.content_generator import MAX_CHART_BYTES, MAX_POST_LEN, ContentGenerator


def test_generate_spread_chart_creates_small_png(tmp_path):
    generator = ContentGenerator(charts_dir=tmp_path)
    chart = generator.generate_spread_chart(
        {
            "opp_id": "OPP-C-CHART",
            "asset": "USDT",
            "market": "ARS",
            "edge_net": 6.1,
            "liquidity": 5713,
        }
    )

    assert chart["size_bytes"] < MAX_CHART_BYTES
    assert chart["path"].endswith(".png")
    assert len(chart["points"]) == 3


def test_generate_professional_post_respects_constraints():
    generator = ContentGenerator()
    post = generator.generate_professional_post(
        {
            "asset": "USDT",
            "market": "ARS",
            "edge_net": 6.1,
            "merchant_count": 12,
            "liquidity": 5713,
            "window": 15,
        },
        {
            "sentiment": {
                "fear_greed_index": 21,
                "fear_greed_label": "Extreme Fear",
                "btc_dominance": 57.4,
            },
            "trending": [{"name": "Asteroid Shiba"}],
        },
    )

    assert len(post) <= MAX_POST_LEN
    assert "$USDT" in post
    assert "?" in post or "¿" in post
    assert "Fear & Greed" in post


def test_publisher_records_chart_data_for_professional_post(tmp_path):
    from clark_kent.publisher import ClarkKent

    publisher = ClarkKent(dry_run=True)
    publisher.storage_file = tmp_path / "published.jsonl"
    publisher.analytics_file = tmp_path / "analytics.jsonl"
    publisher.scheduler.storage_file = publisher.storage_file
    publisher.calendar.storage_file = publisher.storage_file
    publisher.content_generator = ContentGenerator(charts_dir=tmp_path / "charts")
    publisher.scheduler.can_post_now = lambda: True
    publisher.scheduler.can_post_today = lambda: True
    publisher.calendar.validate_post = lambda text: True

    published = publisher.publish(
        {
            "opp_id": "OPP-F-PRO",
            "scanner_id": "F-P2P-CROSS-CURRENCY",
            "type": "F",
            "asset": "USDT",
            "market": "MXN/ARS",
            "buy_fiat": "MXN",
            "sell_fiat": "ARS",
            "edge_net": 4.8,
            "liquidity": 5713,
            "window": 15,
            "route": "MXN→USDT(Binance P2P)→USDT→ARS(Binance P2P)",
        },
        hawk_data={
            "sentiment": {
                "fear_greed_index": 21,
                "fear_greed_label": "Extreme Fear",
                "btc_dominance": 57.4,
            },
            "trending": [{"name": "Asteroid Shiba"}],
        },
    )

    assert published is True
    payload = json.loads(publisher.storage_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["chart"]["size_bytes"] < MAX_CHART_BYTES
    assert "?" in payload["post"] or "¿" in payload["post"]
