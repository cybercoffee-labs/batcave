"""Pump-risk checks for HAWKGIRL trending assets."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = MODULE_DIR / "storage"
TRENDING_HISTORY_FILE = STORAGE_DIR / "trending_history.jsonl"


class PumpDetector:
    """Flag suspicious low-cap trend spikes."""

    PUMP_THRESHOLD_24H = 15.0

    def __init__(self, history_file: Path | None = None):
        self.history_file = history_file or TRENDING_HISTORY_FILE
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_history(self) -> dict[str, dict[str, Any]]:
        history: dict[str, dict[str, Any]] = {}
        if not self.history_file.exists():
            return history

        with open(self.history_file, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                coin_id = str(record.get("id") or "")
                if coin_id:
                    history[coin_id] = record
        return history

    def _append_history(self, trending_coins: list[dict[str, Any]]) -> None:
        timestamp = datetime.now(UTC).isoformat()
        with open(self.history_file, "a", encoding="utf-8") as handle:
            for coin in trending_coins:
                record = {
                    "ts": timestamp,
                    "id": coin.get("id"),
                    "symbol": coin.get("symbol"),
                    "price_change_24h": coin.get("price_change_24h"),
                    "market_cap_rank": coin.get("market_cap_rank"),
                }
                handle.write(json.dumps(record, default=str) + "\n")

    def _risk_level(self, price_change: float) -> str:
        if price_change >= 50:
            return "extreme"
        if price_change >= 30:
            return "very_high"
        return "high"

    def check_for_pumps(self, trending_coins: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Flag suspicious low-cap coins with sharp trend-driven moves."""
        history = self._load_history()
        alerts: list[dict[str, Any]] = []

        for coin in trending_coins:
            coin_id = str(coin.get("id") or "")
            price_change = float(coin.get("price_change_24h", 0.0) or 0.0)
            market_cap_rank = int(coin.get("market_cap_rank", 999999) or 999999)
            recently_appeared = coin_id not in history
            if price_change > self.PUMP_THRESHOLD_24H and market_cap_rank > 200 and recently_appeared:
                risk_level = self._risk_level(price_change)
                alerts.append(
                    {
                        "name": coin.get("name"),
                        "symbol": coin.get("symbol"),
                        "price_change_24h": price_change,
                        "risk_level": risk_level,
                        "warning": (
                            f"{coin.get('symbol')} sube {price_change:.1f}% en 24h con rank {market_cap_rank}; "
                            "posible pump de narrativa, esperar confirmacion."
                        ),
                    }
                )

        self._append_history(trending_coins)
        return alerts
