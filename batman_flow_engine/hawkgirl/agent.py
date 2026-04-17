"""HAWKGIRL agent orchestration."""

from __future__ import annotations

from typing import Any

from hawkgirl.narrative_detector import NarrativeDetector
from hawkgirl.pump_detector import PumpDetector
from hawkgirl.sentiment import SentimentAnalyzer


class HawkgirlAgent:
    """Combine public sentiment, narrative, and pump-risk signals."""

    def __init__(
        self,
        sentiment_analyzer: SentimentAnalyzer | None = None,
        narrative_detector: NarrativeDetector | None = None,
        pump_detector: PumpDetector | None = None,
    ):
        self.sentiment_analyzer = sentiment_analyzer or SentimentAnalyzer()
        self.narrative_detector = narrative_detector or NarrativeDetector()
        self.pump_detector = pump_detector or PumpDetector()

    def full_scan(self) -> dict[str, Any]:
        """Run the full HAWKGIRL sentiment and narrative scan."""
        sentiment = self.sentiment_analyzer.get_market_sentiment()
        trending = self.sentiment_analyzer.get_trending_coins()
        narratives = self.narrative_detector.detect_narratives(trending)
        pump_alerts = self.pump_detector.check_for_pumps(trending)

        scan_results = {
            "sentiment": sentiment,
            "trending": trending,
            "narratives": narratives,
            "pump_alerts": pump_alerts,
        }
        scan_results["generated_post"] = self.generate_clark_kent_post(scan_results)
        return scan_results

    def generate_clark_kent_post(self, scan_results: dict[str, Any]) -> str:
        """Generate a concise Clark Kent post from the scan output."""
        sentiment = scan_results["sentiment"]
        top_3_coins = ", ".join(f"${coin['symbol']}" for coin in scan_results["trending"][:3]) or "sin datos"
        lead_narrative = scan_results["narratives"][0]["name"] if scan_results["narratives"] else "sin narrativa dominante"

        return (
            "🦅 Hawkgirl Sentiment Report\n"
            f"Fear & Greed: {sentiment['fear_greed_index']} ({sentiment['fear_greed_label']})\n"
            f"Trending: {top_3_coins}\n"
            f"Narrativa detectada: {lead_narrative}\n"
            f"BTC dominance: {sentiment['btc_dominance']:.1f}%\n"
            "DYOR | Data-driven\n"
            "#crypto #analysis"
        )
