"""Tests for HAWKGIRL sentiment and narrative detection."""

import requests


def test_hawkgirl_imports():
    from hawkgirl.agent import HawkgirlAgent
    from hawkgirl.narrative_detector import NarrativeDetector
    from hawkgirl.pump_detector import PumpDetector
    from hawkgirl.sentiment import SentimentAnalyzer

    assert callable(HawkgirlAgent)
    assert callable(NarrativeDetector)
    assert callable(PumpDetector)
    assert callable(SentimentAnalyzer)


def test_market_sentiment_aggregates_public_sources():
    from hawkgirl.sentiment import SentimentAnalyzer

    analyzer = SentimentAnalyzer()

    def fake_get_json(url, params=None):
        if "alternative.me" in url:
            return {"data": [{"value": "72", "value_classification": "Greed"}]}
        return {
            "data": {
                "market_cap_change_percentage_24h_usd": 2.5,
                "market_cap_percentage": {"btc": 54.2},
            }
        }

    analyzer._get_json = fake_get_json
    sentiment = analyzer.get_market_sentiment()

    assert sentiment["fear_greed_index"] == 72
    assert sentiment["fear_greed_label"] == "Greed"
    assert sentiment["market_cap_change_24h"] == 2.5
    assert sentiment["btc_dominance"] == 54.2
    assert sentiment["sentiment_label"] == "bullish"


def test_trending_coins_sorted_by_price_change():
    from hawkgirl.sentiment import SentimentAnalyzer

    analyzer = SentimentAnalyzer()
    analyzer._get_json = lambda url, params=None: {
        "coins": [
            {"item": {"id": "coin-a", "name": "Coin A", "symbol": "AAA", "market_cap_rank": 300, "data": {"price_change_percentage_24h": {"usd": 4.0}}}},
            {"item": {"id": "coin-b", "name": "Coin B", "symbol": "BBB", "market_cap_rank": 150, "data": {"price_change_percentage_24h": {"usd": 18.0}}}},
            {"item": {"id": "coin-c", "name": "Coin C", "symbol": "CCC", "market_cap_rank": 220, "data": {"price_change_percentage_24h": {"usd": 9.0}}}},
        ]
    }
    analyzer._get_coin_details = lambda coin_id: {"categories": ["Layer 2"], "watchlist_portfolio_users": 100}

    trending = analyzer.get_trending_coins()

    assert [coin["symbol"] for coin in trending] == ["BBB", "CCC", "AAA"]
    assert trending[0]["social_volume"] == 100
    assert trending[0]["categories"] == ["Layer 2"]


def test_trending_coins_fallback_when_details_fail():
    from hawkgirl.sentiment import SentimentAnalyzer

    analyzer = SentimentAnalyzer()
    def fake_get_json(url, params=None):
        if "search/trending" in url:
            return {
                "coins": [
                    {"item": {"id": "coin-a", "name": "Coin A", "symbol": "AAA", "market_cap_rank": 300, "data": {"price_change_percentage_24h": {"usd": 4.0}}}},
                ]
            }
        raise requests.HTTPError("429 Too Many Requests")

    analyzer._get_json = fake_get_json
    trending = analyzer.get_trending_coins()

    assert trending[0]["categories"] == []
    assert trending[0]["social_volume"] == 0
    assert trending[0]["market_cap_rank"] == 300


def test_narrative_detector_finds_clusters():
    from hawkgirl.narrative_detector import NarrativeDetector

    detector = NarrativeDetector()
    narratives = detector.detect_narratives(
        [
            {"symbol": "DOGE", "name": "Dogecoin", "categories": ["Meme"]},
            {"symbol": "SHIB", "name": "Shiba Inu", "categories": ["Meme"]},
            {"symbol": "PEPE", "name": "Pepe", "categories": ["Meme"]},
            {"symbol": "USDT", "name": "Tether", "categories": ["Stablecoin"]},
            {"symbol": "BTC", "name": "Bitcoin", "categories": ["Store of Value"]},
        ]
    )

    labels = {item["name"] for item in narratives}
    assert "meme_season" in labels
    assert "latam_opportunity" in labels


def test_pump_detector_flags_new_low_cap_spikes(tmp_path):
    from hawkgirl.pump_detector import PumpDetector

    detector = PumpDetector(history_file=tmp_path / "history.jsonl")
    alerts = detector.check_for_pumps(
        [
            {"id": "coin-a", "name": "Coin A", "symbol": "AAA", "price_change_24h": 34.0, "market_cap_rank": 350},
            {"id": "coin-b", "name": "Coin B", "symbol": "BBB", "price_change_24h": 5.0, "market_cap_rank": 50},
        ]
    )

    assert len(alerts) == 1
    assert alerts[0]["symbol"] == "AAA"
    assert alerts[0]["risk_level"] == "very_high"

    second_pass = detector.check_for_pumps(
        [{"id": "coin-a", "name": "Coin A", "symbol": "AAA", "price_change_24h": 34.0, "market_cap_rank": 350}]
    )
    assert second_pass == []


def test_hawkgirl_agent_builds_post():
    from hawkgirl.agent import HawkgirlAgent

    class DummySentiment:
        def get_market_sentiment(self):
            return {
                "fear_greed_index": 61,
                "fear_greed_label": "Greed",
                "market_cap_change_24h": 1.2,
                "btc_dominance": 53.4,
                "sentiment_label": "bullish",
            }

        def get_trending_coins(self):
            return [
                {"symbol": "FET", "name": "Fetch.ai", "price_change_24h": 22.0, "market_cap_rank": 80},
                {"symbol": "RNDR", "name": "Render", "price_change_24h": 16.0, "market_cap_rank": 45},
                {"symbol": "TAO", "name": "Bittensor", "price_change_24h": 14.0, "market_cap_rank": 33},
            ]

    class DummyNarratives:
        def detect_narratives(self, trending_coins):
            return [{"name": "ai_narrative", "tokens": ["FET", "RNDR", "TAO"], "count": 3}]

    class DummyPumps:
        def check_for_pumps(self, trending_coins):
            return []

    agent = HawkgirlAgent(
        sentiment_analyzer=DummySentiment(),
        narrative_detector=DummyNarratives(),
        pump_detector=DummyPumps(),
    )
    scan = agent.full_scan()

    assert scan["narratives"][0]["name"] == "ai_narrative"
    assert "Fear & Greed: 61 (Greed)" in scan["generated_post"]
    assert "Narrativa detectada: ai_narrative" in scan["generated_post"]
