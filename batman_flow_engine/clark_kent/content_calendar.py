"""Content generation and validation helpers for Clark Kent V2."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = MODULE_DIR / "storage"
PUBLISHED_FILE = STORAGE_DIR / "published.jsonl"
MAX_POST_LEN = 280


class ContentCalendar:
    """Generate compliant Clark Kent content variations."""

    STABLECOINS = ["$USDT", "$USDC", "$DAI"]

    def __init__(self, storage_file: Path | None = None):
        self.storage_file = Path(storage_file) if storage_file else PUBLISHED_FILE

    def get_daily_analysis(self, opportunities: list) -> str:
        todays_items = opportunities or self._records_for_days(1)
        count = len(todays_items)
        best_market = self._best_market(todays_items)
        avg_edge = self._average_metric(todays_items, ["edge_net", "spread", "edge_pct", "profit_pct"])
        post = (
            f"📊 Resumen Batcave — {datetime.now().date().isoformat()}\n"
            f"$USDT: {count} oportunidades detectadas\n"
            f"Mejor mercado: {best_market}\n"
            f"Edge promedio: {avg_edge:.1f}%\n"
            "#crypto #trading"
        )
        return self._ensure_valid(post)

    def get_weekly_summary(self) -> str:
        if datetime.now().weekday() != 0:
            return self._ensure_valid(
                "📈 Semana Batcave\n$USDT: 0 oportunidades\nWin rate: 0%\nMejor día: Próximo lunes\n#crypto #weekly"
            )

        records = self._records_for_days(7)
        total_opportunities = len(records)
        profitable = sum(
            1
            for record in records
            if float(record.get("edge_net", record.get("spread", record.get("edge_pct", 0.0))) or 0.0) > 0
        )
        win_rate = (profitable / total_opportunities * 100) if total_opportunities else 0.0
        best_day = self._best_day(records)
        post = (
            "📈 Semana Batcave\n"
            f"$USDT: {total_opportunities} oportunidades\n"
            f"Win rate: {win_rate:.0f}%\n"
            f"Mejor día: {best_day}\n"
            "#crypto #weekly"
        )
        return self._ensure_valid(post)

    def get_market_insight(self, opportunity: dict) -> str:
        asset = str(opportunity.get("asset", "BTC")).upper().lstrip("$")
        pattern = opportunity.get("pattern", "flujo defensivo")
        volume_status = opportunity.get("volume_status", "estable")
        trend = opportunity.get("trend", "neutral")
        asset_label = asset if asset == "USDT" else asset
        post = (
            "🧠 Market Intel\n"
            f"$USDT vs {asset_label}: {pattern}\n"
            f"Volumen: {volume_status}\n"
            f"Tendencia: {trend}\n"
            "#crypto #analysis"
        )
        return self._ensure_valid(post)

    def get_stablecoin_focus(self, opportunities: list) -> str:
        items = opportunities or self._records_for_days(1)
        usdt_spread = self._average_for_asset(items, "USDT")
        usdc_spread = self._average_for_asset(items, "USDC")
        best_exchange = self._best_exchange(items)
        post = (
            "💰 Stablecoin Watch\n"
            f"$USDT spread: {usdt_spread:.2f}%\n"
            f"$USDC spread: {usdc_spread:.2f}%\n"
            f"Mejor opción hoy: {best_exchange}\n"
            "#crypto #stablecoins"
        )
        return self._ensure_valid(post)

    def validate_post(self, post: str) -> bool:
        cashtags = re.findall(r"\$[A-Z0-9]+", post)
        hashtags = re.findall(r"(?<!\$)#[A-Za-z][A-Za-z0-9_]*", post)
        has_stablecoin = any(tag in self.STABLECOINS for tag in cashtags)
        return (
            len(post) < MAX_POST_LEN
            and has_stablecoin
            and len(cashtags) <= 2
            and len(hashtags) <= 2
        )

    def _ensure_valid(self, post: str) -> str:
        if self.validate_post(post):
            return post

        cleaned = post.replace("$DAI", "DAI").replace("$USDC", "USDC")
        cashtags = re.findall(r"\$[A-Z0-9]+", cleaned)
        if not any(tag in self.STABLECOINS for tag in cashtags):
            cleaned = f"$USDT\n{cleaned}"
        cleaned_lines = cleaned.splitlines()
        trimmed = "\n".join(cleaned_lines[:5])
        hashtags = re.findall(r"(?<!\$)#[A-Za-z][A-Za-z0-9_]*", trimmed)
        if len(hashtags) > 2:
            trimmed = re.sub(r"(?<!\$)#[A-Za-z][A-Za-z0-9_]*", "", trimmed, count=len(hashtags) - 2).strip()
        return trimmed[: MAX_POST_LEN - 1]

    def _records_for_days(self, days: int) -> list[dict]:
        if not self.storage_file.exists():
            return []

        cutoff = datetime.now() - timedelta(days=max(days - 1, 0))
        records: list[dict] = []
        with open(self.storage_file, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    opportunity = row.get("opportunity", row)
                    ts = row.get("ts")
                    if not ts:
                        continue
                    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                    if parsed >= cutoff:
                        if isinstance(opportunity, dict):
                            records.append({**opportunity, "ts": ts})
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
        return records

    def _average_metric(self, items: list[dict], keys: list[str]) -> float:
        values: list[float] = []
        for item in items:
            for key in keys:
                value = item.get(key)
                if value is not None:
                    try:
                        values.append(float(value))
                        break
                    except (TypeError, ValueError):
                        continue
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _best_market(self, items: list[dict]) -> str:
        if not items:
            return "MXN"
        markets = [str(item.get("sell_exchange") or item.get("market") or "MXN") for item in items]
        for preferred in ("ARS", "MXN", "COP", "VES"):
            for market in markets:
                if preferred in market:
                    return market
        return Counter(markets).most_common(1)[0][0]

    def _best_day(self, items: list[dict]) -> str:
        if not items:
            return "Sin datos"
        counts: Counter[str] = Counter()
        for item in items:
            ts = item.get("ts")
            if not ts:
                continue
            try:
                day = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%A")
            except ValueError:
                continue
            counts[day] += 1
        return counts.most_common(1)[0][0] if counts else "Sin datos"

    def _average_for_asset(self, items: list[dict], asset: str) -> float:
        spreads = []
        for item in items:
            raw_asset = str(item.get("asset", "")).upper().lstrip("$")
            if raw_asset != asset:
                continue
            value = item.get("spread", item.get("edge_net", 0.0))
            try:
                spreads.append(float(value))
            except (TypeError, ValueError):
                continue
        if not spreads:
            return 0.0
        return sum(spreads) / len(spreads)

    def _best_exchange(self, items: list[dict]) -> str:
        if not items:
            return "Binance MXN"
        ranked = sorted(
            items,
            key=lambda item: float(item.get("spread", item.get("edge_net", 0.0)) or 0.0),
            reverse=True,
        )
        top = ranked[0]
        return str(top.get("sell_exchange") or top.get("exchange") or "Binance MXN")
