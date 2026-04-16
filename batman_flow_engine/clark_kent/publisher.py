"""
Clark Kent — Batcave Publisher for Binance Square

Publishes short Batcave opportunity posts in dry-run mode by default.
"""

import json
import logging
import os
import re
import ssl
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clark_kent.content_calendar import ContentCalendar
from clark_kent.scheduler import PostScheduler

logger = logging.getLogger("batman.clark_kent")

BASE_DIR = Path(__file__).resolve().parent.parent
MODULE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = MODULE_DIR / "storage"
PUBLISHED_FILE = STORAGE_DIR / "published.jsonl"
ANALYTICS_FILE = STORAGE_DIR / "analytics.jsonl"
BINANCE_SQUARE_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/publish"
MAX_POST_LEN = 280
MIN_EDGE_THRESHOLD = 3.0
ALLOWED_STABLECOINS = {"USDT", "USDC", "DAI"}


def _load_env() -> None:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


class ClarkKent:
    """Short-form publisher for Binance Square opportunities."""

    TEMPLATES = {
        "p2p": "🦇 P2P Alert\n{primary_cashtag} detectado: {edge_net:.1f}% edge neto\n{buy_exchange} → {sell_exchange}\nVentana: ~{window} min\n#crypto #P2P",
        "cross": "🦇 Spread Alert\n{primary_cashtag}: {spread:.2f}% entre exchanges\nOportunidad de arbitraje detectada\n#crypto #arbitrage",
        "funding": "🦇 Funding Rate\n{primary_cashtag}: {rate:.4f}% ({apy:.1f}% APY)\nExchange: {exchange}\n#crypto #DeFi",
        "general": "🦇 Batcave Intel\n{primary_cashtag} {summary}\n#crypto #trading",
    }

    def __init__(self, dry_run: bool = True):
        _load_env()
        self.api_key = os.environ.get("BINANCE_SQUARE_API_KEY", "")
        self.dry_run = dry_run
        self.storage_file = PUBLISHED_FILE
        self.analytics_file = ANALYTICS_FILE
        self.scheduler = PostScheduler(storage_file=self.storage_file)
        self.calendar = ContentCalendar(storage_file=self.storage_file)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)

    def publish(self, opportunity: dict) -> bool:
        """Publish a qualifying opportunity to Binance Square or print it in dry-run mode."""
        edge_value = self._edge_value(opportunity)
        if edge_value < MIN_EDGE_THRESHOLD:
            logger.info("Skipping post below threshold: %.2f%%", edge_value)
            self._append_log(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "status": "skipped",
                    "reason": "below_threshold",
                    "edge_value": edge_value,
                    "dry_run": self.dry_run,
                    "opportunity": opportunity,
                }
            )
            return False

        if not self.scheduler.can_post_now():
            next_window = self.scheduler.next_optimal_hour()
            logger.info("Queued for next window: %s", next_window)
            self._append_log(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "status": "queued",
                    "reason": "outside_optimal_window",
                    "next_window": next_window,
                    "dry_run": self.dry_run,
                    "opportunity": opportunity,
                }
            )
            return False

        if not self.scheduler.can_post_today():
            logger.info("Daily post limit reached: %s", self.scheduler.posts_today())
            self._append_log(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "status": "queued",
                    "reason": "daily_limit_reached",
                    "posts_today": self.scheduler.posts_today(),
                    "dry_run": self.dry_run,
                    "opportunity": opportunity,
                }
            )
            return False

        template = self._select_template(str(opportunity.get("type", "")))
        post_text = self._format_post(template, opportunity)
        if not self.calendar.validate_post(post_text):
            logger.error("Rejected post due to cashtag/hashtag compliance: %s", post_text)
            self._append_log(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "status": "rejected",
                    "reason": "invalid_post_format",
                    "dry_run": self.dry_run,
                    "post": post_text,
                    "opportunity": opportunity,
                }
            )
            return False

        record = {
            "ts": datetime.now(UTC).isoformat(),
            "status": "ok",
            "dry_run": self.dry_run,
            "post": post_text,
            "opportunity": opportunity,
        }

        if self.dry_run:
            print(post_text)
            logger.info("Dry run post generated (%d chars)", len(post_text))
            self._append_log(record)
            self._append_analytics(post_text, opportunity, platform="binance_square")
            return True

        success = self._post_to_square(post_text)
        record["status"] = "sent" if success else "error"
        self._append_log(record)
        if success:
            self._append_analytics(post_text, opportunity, platform="binance_square")
        return success

    def _select_template(self, opp_type: str) -> str:
        """Choose the post template based on opportunity type."""
        normalized = opp_type.upper().strip()
        if normalized in {"C", "P2P", "P2P_LATAM", "P2P_CROSS"}:
            return self.TEMPLATES["p2p"]
        if normalized in {"D", "CROSS", "CROSS_EXCHANGE", "MULTI_EXCHANGE"}:
            return self.TEMPLATES["cross"]
        if normalized in {"F", "FUNDING", "FUNDING_RATE"}:
            return self.TEMPLATES["funding"]
        return self.TEMPLATES["general"]

    def _format_post(self, template: str, data: dict) -> str:
        """Format a Binance Square post and keep it under 280 characters."""
        asset = str(data.get("asset", "UNKNOWN")).lstrip("$")
        stablecoin = self._stablecoin_cashtag(data)
        payload = {
            "market": data.get("market", data.get("asset", "UNKNOWN")),
            "edge_net": float(data.get("edge_net", data.get("spread", 0.0)) or 0.0),
            "buy_exchange": data.get("buy_exchange", "N/A"),
            "sell_exchange": data.get("sell_exchange", "N/A"),
            "asset": asset,
            "primary_cashtag": stablecoin,
            "spread": float(data.get("spread", data.get("edge_net", 0.0)) or 0.0),
            "rate": float(data.get("rate", data.get("funding_rate", 0.0)) or 0.0),
            "apy": float(data.get("apy", data.get("annualized_pct", 0.0)) or 0.0),
            "exchange": data.get("exchange", "UNKNOWN"),
            "window": data.get("window", "N/A"),
            "summary": self._summary_from_data(data),
        }

        post = template.format(**payload)
        if len(post) <= MAX_POST_LEN:
            return post

        fallback_template = template.replace(" #crypto #P2P", "").replace(" #crypto #arbitrage", "")
        fallback_template = fallback_template.replace(" #crypto #funding", "").replace(" #crypto #trading", "")
        post = fallback_template.format(**payload)
        if len(post) <= MAX_POST_LEN:
            return post

        if "{summary}" in fallback_template:
            fixed_text = fallback_template.format(**{**payload, "summary": ""})
            reserve = len(fixed_text) + 3
            allowed = max(0, MAX_POST_LEN - reserve)
            payload["summary"] = payload["summary"][:allowed].rstrip(" |.") + "..."
            return fallback_template.format(**payload)[:MAX_POST_LEN]

        return post[: MAX_POST_LEN - 3].rstrip() + "..."

    def _stablecoin_cashtag(self, data: dict) -> str:
        """Return a compliant stablecoin cashtag for every Clark Kent post."""
        asset = str(data.get("asset", "")).upper().lstrip("$")
        preferred = str(data.get("stablecoin", "")).upper().lstrip("$")
        for candidate in (preferred, asset, "USDT"):
            if candidate in ALLOWED_STABLECOINS:
                return f"${candidate}"
        return "$USDT"

    def _summary_from_data(self, data: dict) -> str:
        """Build a concise summary for the fallback template."""
        parts = []
        if data.get("market"):
            parts.append(str(data["market"]))
        if data.get("asset"):
            parts.append(str(data["asset"]))
        if data.get("edge_net") is not None:
            parts.append(f"{float(data['edge_net']):.1f}% edge")
        elif data.get("spread") is not None:
            parts.append(f"{float(data['spread']):.2f}% spread")
        if data.get("buy_exchange") and data.get("sell_exchange"):
            parts.append(f"{data['buy_exchange']} -> {data['sell_exchange']}")
        elif data.get("exchange"):
            parts.append(str(data["exchange"]))
        summary = " ".join(parts).strip()
        return summary or "Opportunity detected"

    def _edge_value(self, opportunity: dict) -> float:
        """Extract a comparable edge percentage from the opportunity payload."""
        for key in ("edge_net", "spread", "edge_pct", "profit_pct"):
            value = opportunity.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

    def _post_to_square(self, post_text: str) -> bool:
        """Send a live post to Binance Square."""
        if not self.api_key:
            logger.error("BINANCE_SQUARE_API_KEY is not configured")
            return False

        payload = json.dumps({"content": post_text}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "batman-flow-engine/1.0",
            "X-MBX-APIKEY": self.api_key,
        }

        try:
            request = urllib.request.Request(  # noqa: S310
                BINANCE_SQUARE_URL,
                data=payload,
                headers=headers,
                method="POST",
            )
            context = ssl.create_default_context()
            with urllib.request.urlopen(request, timeout=15, context=context) as response:  # noqa: S310
                status_code = getattr(response, "status", 200)
                success = 200 <= status_code < 300
                if success:
                    logger.info("Published post to Binance Square")
                else:
                    logger.error("Binance Square publish failed with status %s", status_code)
                return success
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
            logger.error("Binance Square API error %s: %s", exc.code, body[:200])
        except Exception as exc:
            logger.error("Binance Square publish failed: %s", exc)
        return False

    def _append_log(self, record: dict[str, Any]) -> bool:
        """Append a publish record to JSONL storage."""
        try:
            with open(self.storage_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")
            return True
        except Exception as exc:
            logger.error("Failed to write Clark Kent log: %s", exc)
            return False

    def _append_analytics(self, post_text: str, opportunity: dict[str, Any], platform: str) -> bool:
        """Append lightweight analytics estimates for downstream reporting."""
        cashtags = re.findall(r"\$[A-Z0-9]+", post_text)
        hashtags = re.findall(r"(?<!\$)#[A-Za-z][A-Za-z0-9_]*", post_text)
        opportunity_type = str(opportunity.get("type", "general")).lower() or "general"
        analytics = {
            "ts": datetime.now(UTC).isoformat(),
            "type": opportunity_type,
            "platform": platform,
            "char_count": len(post_text),
            "cashtags": cashtags,
            "hashtags": hashtags,
            "estimated_views": 120 + (25 * len(hashtags)) + (15 * len(cashtags)),
            "engagement_estimate": round(0.8 + (0.15 * len(hashtags)) + (0.1 * len(cashtags)), 2),
        }
        try:
            with open(self.analytics_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(analytics, default=str) + "\n")
            return True
        except Exception as exc:
            logger.error("Failed to write Clark Kent analytics: %s", exc)
            return False
