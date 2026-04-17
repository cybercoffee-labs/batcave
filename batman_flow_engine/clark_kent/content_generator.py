"""Professional content generation helpers for Clark Kent."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

MODULE_DIR = Path(__file__).resolve().parent
CHARTS_DIR = MODULE_DIR / "storage" / "charts"
MAX_CHART_BYTES = 100 * 1024
MAX_POST_LEN = 500


class ContentGenerator:
    """Generate professional Clark Kent posts and lightweight chart assets."""

    def __init__(self, charts_dir: Path | None = None):
        self.charts_dir = charts_dir or CHARTS_DIR
        self.charts_dir.mkdir(parents=True, exist_ok=True)
        self.last_chart_data: dict[str, Any] = {}

    def generate_spread_chart(self, opportunity: dict[str, Any]) -> dict[str, Any]:
        """Create a lightweight spread chart under 100KB."""
        edge_net = self._float_value(opportunity, "edge_net", "cross_premium_spread", "merchant_spread_pct")
        liquidity = self._float_value(opportunity, "liquidity", "depth_estimate", "depth_buy_usd", "estimated_pnl_usd")
        baseline = max(edge_net - 1.2, 0.2)
        confirmation = max(edge_net - 0.5, 0.2)
        points = [round(baseline, 2), round(confirmation, 2), round(edge_net, 2)]
        labels = ["Base", "Live", "Net"]

        asset = str(opportunity.get("asset", "USDT")).upper().lstrip("$")
        market = str(opportunity.get("market", "market"))
        opp_id = str(opportunity.get("opp_id", "chart"))
        chart_path = self.charts_dir / f"{opp_id}.png"

        fig, ax = plt.subplots(figsize=(3.4, 1.8), dpi=72)
        fig.patch.set_facecolor("#f7f5ef")
        ax.set_facecolor("#f7f5ef")
        ax.plot(labels, points, color="#0b6e4f", linewidth=2.0, marker="o", markersize=4)
        ax.fill_between(labels, points, [0.0, 0.0, 0.0], color="#0b6e4f", alpha=0.08)
        ax.set_title(f"{asset}/{market} spread", fontsize=9, fontweight="bold")
        ax.set_ylabel("%", fontsize=8)
        ax.tick_params(axis="x", labelsize=8)
        ax.tick_params(axis="y", labelsize=7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        ax.text(2, points[-1], f"{edge_net:.1f}%", fontsize=8, ha="right", va="bottom")
        if liquidity:
            ax.text(0, max(points) * 0.86, f"liq ${liquidity:,.0f}", fontsize=7, color="#5b5b5b")

        buffer = BytesIO()
        fig.tight_layout(pad=0.6)
        fig.savefig(buffer, format="png", dpi=72, bbox_inches="tight")
        plt.close(fig)
        raw = buffer.getvalue()

        if len(raw) > MAX_CHART_BYTES:
            raw = self._downsample_chart(points, labels, asset, market, liquidity)

        chart_path.write_bytes(raw)
        self.last_chart_data = {
            "path": str(chart_path),
            "size_bytes": len(raw),
            "points": points,
            "labels": labels,
        }
        return dict(self.last_chart_data)

    def generate_engagement_question(self, market: str) -> str:
        """Return a short engagement question by market."""
        market_label = str(market or "mercado").upper()
        if "ARS" in market_label:
            return "¿Entrarías a $USDT/ARS hoy o esperarías mejor premium?"
        if "MXN" in market_label:
            return "¿Ves espacio para otro rebote en $USDT/MXN esta sesión?"
        if "VES" in market_label:
            return "¿Tomarías esta ruta $USDT/VES o exigirías más confirmación?"
        if "COP" in market_label:
            return "¿Te convence este spread $USDT/COP para arbitraje rápido?"
        return "¿Tomarías esta oportunidad ahora o esperarías confirmación adicional?"

    def generate_professional_post(self, opportunity: dict[str, Any], hawk_data: dict[str, Any] | None = None) -> str:
        """Generate a professional post under 500 chars with context and a question."""
        hawk_data = hawk_data or {}
        sentiment = hawk_data.get("sentiment", {})
        trending = hawk_data.get("trending", [])

        asset = str(opportunity.get("asset", "USDT")).upper().lstrip("$")
        market = str(opportunity.get("market", "market"))
        edge_net = self._float_value(opportunity, "edge_net", "cross_premium_spread", "merchant_spread_pct")
        liquidity = self._float_value(opportunity, "liquidity", "depth_estimate", "depth_buy_usd", "estimated_pnl_usd")
        merchant_count = max(
            int(opportunity.get("merchant_count", 0) or 0),
            int(opportunity.get("num_buy_ads", 0) or 0),
            int(opportunity.get("num_sell_ads", 0) or 0),
        )
        window = str(opportunity.get("window") or opportunity.get("network_time_mins") or 15)
        fear = sentiment.get("fear_greed_index", "N/A")
        fear_label = sentiment.get("fear_greed_label", "Neutral")
        btc_dom = float(sentiment.get("btc_dominance", 0.0) or 0.0)
        trend_name = trending[0]["name"] if trending else "sin dominante"
        question = self.generate_engagement_question(market)
        liquidity_label = f"${liquidity:,.0f}" if liquidity else "N/A"

        post = (
            f"📊 ${asset}/{market} spread {edge_net:.1f}% neto.\n"
            f"Liquidez: {liquidity_label} | señales: {merchant_count} | ventana: {window}m.\n"
            f"Contexto: Fear & Greed {fear} ({fear_label}), BTC dom {btc_dom:.1f}%, trending {trend_name}.\n"
            f"{question}\n"
            "#crypto #analysis"
        )
        return self._trim_post(post)

    def _downsample_chart(
        self,
        points: list[float],
        labels: list[str],
        asset: str,
        market: str,
        liquidity: float,
    ) -> bytes:
        fig, ax = plt.subplots(figsize=(3.0, 1.6), dpi=60)
        fig.patch.set_facecolor("#f7f5ef")
        ax.bar(labels, points, color="#0b6e4f", alpha=0.85)
        ax.set_title(f"{asset}/{market}", fontsize=8, fontweight="bold")
        ax.tick_params(axis="x", labelsize=7)
        ax.tick_params(axis="y", labelsize=7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if liquidity:
            ax.text(0, max(points) * 0.82, f"liq ${liquidity:,.0f}", fontsize=6)
        buffer = BytesIO()
        fig.tight_layout(pad=0.5)
        fig.savefig(buffer, format="png", dpi=60, bbox_inches="tight")
        plt.close(fig)
        return buffer.getvalue()

    def _trim_post(self, post: str) -> str:
        text = re.sub(r"[ \t]+", " ", post).strip()
        if len(text) <= MAX_POST_LEN:
            return text
        question_split = text.split("\n")
        while len("\n".join(question_split)) > MAX_POST_LEN and len(question_split) > 3:
            question_split.pop(1)
        trimmed = "\n".join(question_split)
        return trimmed[:MAX_POST_LEN].rstrip()

    def _float_value(self, data: dict[str, Any], *keys: str) -> float:
        for key in keys:
            value = data.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0
