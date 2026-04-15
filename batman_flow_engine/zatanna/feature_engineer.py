"""Feature extraction for ZATANNA opportunity classification."""

from __future__ import annotations

from datetime import datetime
from typing import Any


class FeatureEngineer:
    def extract_features(self, opportunity: dict) -> dict:
        """Extract ML features from raw opportunity."""
        timestamp = self._parse_timestamp(opportunity.get("ts"))
        return {
            "hour": timestamp.hour,
            "day_of_week": timestamp.weekday(),
            "scanner_type": opportunity.get("type", "unknown"),
            "edge_net": float(opportunity.get("edge_net", 0) or 0),
            "spread": self._extract_spread(opportunity),
            "volume": float(opportunity.get("depth_estimate", 0) or 0),
            "market": opportunity.get("market", "unknown"),
            "exchange": self._extract_exchange(opportunity),
            "merchant_count": int(opportunity.get("merchant_count", 0) or 0),
            "depth_estimate": float(opportunity.get("depth_estimate", 0) or 0),
        }

    def _extract_spread(self, opportunity: dict[str, Any]) -> float:
        for key in ("spread", "spread_pct", "merchant_spread", "cross_premium_spread", "basis_pct"):
            value = opportunity.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    def _extract_exchange(self, opportunity: dict[str, Any]) -> str:
        for key in ("exchange", "buy_exchange", "sell_exchange", "venue"):
            value = opportunity.get(key)
            if value:
                return str(value)
        return "unknown"

    def _parse_timestamp(self, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if not value:
            return datetime.fromisoformat("1970-01-01T00:00:00")
        normalized = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return datetime.fromisoformat("1970-01-01T00:00:00")
