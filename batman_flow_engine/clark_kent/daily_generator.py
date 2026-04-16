"""Daily Binance Square post generator backed by AQUAMAN liquidity checks."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from core.aquaman import Aquaman
from zatanna.predictor import ZatannaPredictor


REPORT_PATH = Path("storage/reports/ready_to_post.txt")
OPPORTUNITIES_PATH = Path("storage/logs/opportunities.jsonl")
MAX_POST_LEN = 280
STABLECOINS = {"USDT", "USDC", "DAI"}


class DailyPostGenerator:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.aquaman = Aquaman(dry_run=dry_run)
        self.predictor = ZatannaPredictor()
        self.opportunities_path = OPPORTUNITIES_PATH
        self.last_verified: list[dict[str, Any]] = []
        self.last_market_summary: dict[str, Any] = {}

    def generate_and_save(self) -> list[dict[str, str]]:
        """Generate 4 posts and save them to ready_to_post.txt."""
        posts = self.generate_daily_posts()
        self._save_to_file(posts)
        self._print_posts(posts)
        return posts

    def generate_daily_posts(self) -> list[dict[str, str]]:
        data = self._load_recent_data()
        verified = self._filter_with_aquaman(data)
        self.last_verified = verified
        self.last_market_summary = self.aquaman.get_market_summary()

        posts = [
            self._morning_alpha(verified),
            self._stablecoin_depth(verified),
            self._top_liquid_opportunity(verified),
            self._zatanna_prediction(verified),
        ]
        return posts

    def _load_recent_data(self) -> list[dict[str, Any]]:
        if not self.opportunities_path.exists():
            return []

        cutoff = datetime.now(UTC) - timedelta(days=1)
        rows: list[dict[str, Any]] = []
        with open(self.opportunities_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    ts = datetime.fromisoformat(str(row.get("ts", "")).replace("Z", "+00:00"))
                    if ts >= cutoff:
                        rows.append(row)
                except Exception:
                    continue
        return rows[-250:]

    def _morning_alpha(self, data: list[dict[str, Any]]) -> dict[str, str]:
        count = len(data)
        markets = Counter(self._market_name(item) for item in data if self._market_name(item))
        best_market = markets.most_common(1)[0][0] if markets else "Sin señales"
        avg_edge = sum(float(item.get("edge_net", 0.0) or 0.0) for item in data) / count if count else 0.0
        content = (
            "📊 Batcave Morning Alpha\n"
            f"$USDT: {count} señales verificadas\n"
            f"Mejor mercado: {best_market}\n"
            f"Edge promedio: {avg_edge:.1f}%\n"
            "Data-driven analysis, DYOR\n"
            "#crypto #trading"
        )
        return self._build_post("08:00 AM", "morning_alpha", content)

    def _stablecoin_depth(self, data: list[dict[str, Any]]) -> dict[str, str]:
        summary = self.last_market_summary or self.aquaman.get_market_summary()
        best_market = summary.get("best_market") or {}
        depth_usd = float(best_market.get("depth_usd", 0.0) or 0.0)
        spread = float(best_market.get("spread_pct", 0.0) or 0.0)
        slippage = float(best_market.get("slippage_pct", 0.0) or 0.0)
        symbol = best_market.get("symbol", "BTC/USDT")
        content = (
            "💰 Stablecoin Depth Report\n"
            f"$USDT profundidad: {depth_usd:,.0f} USD\n"
            f"{symbol} spread: {spread:.3f}%\n"
            f"Slippage estimado 100 USD: {slippage:.2f}%\n"
            "Data-driven analysis, DYOR\n"
            "#crypto #stablecoins"
        )
        return self._build_post("12:00 PM", "stablecoin_depth", content)

    def _top_liquid_opportunity(self, data: list[dict[str, Any]]) -> dict[str, str]:
        best = max(data, key=lambda item: float(item.get("edge_net", 0.0) or 0.0), default=None)
        if best is None:
            content = (
                "🦇 Top Verified Signal\n"
                "$USDT: sin señal líquida hoy\n"
                "Liquidez verificada: 0 USD\n"
                "Slippage: 0.00%\n"
                "Data-driven analysis, DYOR\n"
                "#crypto #P2P"
            )
            return self._build_post("06:00 PM", "top_signal", content)

        liquidity = best.get("liquidity", {})
        symbol = str(liquidity.get("symbol") or f"{best.get('asset', 'USDT')}/USDT")
        pair = self._cashtag_pair_from_symbol(symbol)
        edge = float(best.get("edge_net", 0.0) or 0.0)
        depth = float(liquidity.get("depth_usd", 0.0) or 0.0)
        slippage = float(liquidity.get("slippage_pct", 0.0) or 0.0)
        content = (
            "🦇 Top Verified Signal\n"
            f"{pair}: {edge:.2f}% edge\n"
            f"Liquidez verificada: {depth:,.0f} USD\n"
            f"Slippage: {slippage:.2f}%\n"
            "Data-driven analysis, DYOR\n"
            "#crypto #P2P"
        )
        return self._build_post("06:00 PM", "top_signal", content)

    def _zatanna_prediction(self, data: list[dict[str, Any]]) -> dict[str, str]:
        base = max(data, key=lambda item: float(item.get("edge_net", 0.0) or 0.0), default={})
        prediction = self._predict_with_fallback(base, data)
        label = {
            "strong_buy": "sesgo alcista",
            "buy": "sesgo positivo",
            "hold": "sesgo neutral",
            "skip": "sesgo defensivo",
        }.get(prediction["recommendation"], "sesgo neutral")
        confidence_pct = int(round(float(prediction.get("probability", 0.0)) * 100))
        content = (
            "🧠 Zatanna ML Insight\n"
            f"$USDT: {label} para mañana\n"
            f"Confianza: {confidence_pct:.0f}%\n"
            f"Basado en {len(data)} datos analizados\n"
            "Data-driven analysis, DYOR\n"
            "#crypto #analysis"
        )
        return self._build_post("09:00 PM", "ml_prediction", content)

    def _predict_with_fallback(self, base: dict[str, Any], data: list[dict[str, Any]]) -> dict[str, Any]:
        if base:
            try:
                return self.predictor.predict(base)
            except Exception:
                pass

        avg_edge = sum(float(item.get("edge_net", 0.0) or 0.0) for item in data) / len(data) if data else 0.0
        if avg_edge >= 1.5:
            return {"recommendation": "buy", "confidence": "medium", "probability": 0.68}
        if avg_edge >= 0.5:
            return {"recommendation": "hold", "confidence": "medium", "probability": 0.55}
        return {"recommendation": "hold", "confidence": "low", "probability": 0.5}

    def _filter_with_aquaman(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Anti-Joker filter: only keep liquid opportunities."""
        verified: list[dict[str, Any]] = []
        for opp in data:
            try:
                result = self.aquaman.verify_opportunity(opp)
                if result and result.get("is_liquid"):
                    verified.append({**opp, "liquidity": result})
            except Exception:
                continue
        return verified

    def _save_to_file(self, posts: list[dict[str, str]]) -> None:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        output = "🦇 BATCAVE — Daily Posts\n"
        output += f"📅 Fecha: {date.today().isoformat()}\n"
        output += f"✅ Filtrado por AQUAMAN (min $500 USD liquidez)\n"
        output += "=" * 50 + "\n\n"

        for post in posts:
            output += f"⏰ PUBLICAR A LAS {post['time']}\n"
            output += f"📝 Tipo: {post['type']}\n"
            output += "-" * 50 + "\n"
            output += post["content"] + "\n"
            output += "-" * 50 + "\n"
            output += f"📏 Caracteres: {len(post['content'])}\n\n"

        REPORT_PATH.write_text(output, encoding="utf-8")

    def _print_posts(self, posts: list[dict[str, str]]) -> None:
        for post in posts:
            print(f"\n⏰ {post['time']} — {post['type']}")
            print(post["content"])
            print(f"📏 {len(post['content'])} chars")

    def _build_post(self, post_time: str, post_type: str, content: str) -> dict[str, str]:
        normalized = self._normalize_post(content)
        return {"time": post_time, "type": post_type, "content": normalized}

    def _normalize_post(self, content: str) -> str:
        text = content.strip()
        if not any(tag in text for tag in ("$USDT", "$USDC", "$DAI")):
            text = f"$USDT\n{text}"

        hashtags = re.findall(r"(?<!\$)#[A-Za-z][A-Za-z0-9_]*", text)
        if len(hashtags) > 2:
            keep = hashtags[:2]
            body = re.sub(r"(?<!\$)#[A-Za-z][A-Za-z0-9_]*", "", text).strip()
            text = f"{body}\n{' '.join(keep)}"

        cashtags = re.findall(r"\$[A-Z][A-Z0-9]*", text)
        if len(cashtags) > 2:
            allowed = cashtags[:2]
            used = set()

            def replace(match: re.Match[str]) -> str:
                token = match.group(0)
                if token in allowed and token not in used:
                    used.add(token)
                    return token
                return token.lstrip("$")

            text = re.sub(r"\$[A-Z][A-Z0-9]*", replace, text)

        if len(text) >= MAX_POST_LEN:
            text = text[: MAX_POST_LEN - 1].rstrip()
        return text

    def _cashtag_pair(self, opportunity: dict[str, Any]) -> str:
        asset = str(opportunity.get("asset") or "USDT").upper().lstrip("$")
        if asset in STABLECOINS:
            return "$USDT"
        return f"${asset}"

    def _cashtag_pair_from_symbol(self, symbol: str) -> str:
        base, _, quote = symbol.upper().partition("/")
        if not quote:
            return self._cashtag_pair({"asset": base})
        base_tag = f"${base.lstrip('$')}"
        quote_tag = f"${quote.lstrip('$')}"
        if quote.lstrip("$") in STABLECOINS:
            return f"{base_tag}/{quote_tag}"
        return base_tag

    def _market_name(self, opportunity: dict[str, Any]) -> str:
        market = str(opportunity.get("market") or "").upper().strip()
        if "/" in market:
            return market.split("/")[-1]
        if market:
            return market
        asset = str(opportunity.get("asset") or "USDT").upper().strip()
        return asset
