"""Bybit Square publisher for Clark Kent content."""

from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clark_kent.publisher import _load_env


logger = logging.getLogger("batman.clark_kent.bybit")

MODULE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = MODULE_DIR / "storage"
BYBIT_PUBLISHED_FILE = STORAGE_DIR / "bybit_published.jsonl"
BYBIT_ANALYTICS_FILE = STORAGE_DIR / "bybit_analytics.jsonl"
BYBIT_SQUARE_URL = "https://api.bybit.com/v5/social/post/create"


class BybitPublisher:
    """Publish Clark Kent content to Bybit Square."""

    def __init__(self, dry_run: bool = True):
        _load_env()
        self.api_key = os.environ.get("BYBIT_SQUARE_API_KEY", "")
        self.dry_run = dry_run
        self.storage_file = BYBIT_PUBLISHED_FILE
        self.analytics_file = BYBIT_ANALYTICS_FILE
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)

    def publish(self, content: str) -> bool:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "platform": "bybit_square",
            "dry_run": self.dry_run,
            "content": content,
        }
        if self.dry_run:
            print(f"[BYBIT DRY] {content}")
            record["status"] = "ok"
            self._append_log(record)
            self._append_analytics(content)
            return True

        if not self.api_key:
            logger.error("BYBIT_SQUARE_API_KEY is not configured")
            record["status"] = "error"
            record["reason"] = "missing_api_key"
            self._append_log(record)
            return False

        payload = json.dumps({"content": content}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "batman-flow-engine/1.0",
            "X-BAPI-API-KEY": self.api_key,
        }

        try:
            request = urllib.request.Request(  # noqa: S310
                BYBIT_SQUARE_URL,
                data=payload,
                headers=headers,
                method="POST",
            )
            context = ssl.create_default_context()
            with urllib.request.urlopen(request, timeout=15, context=context) as response:  # noqa: S310
                status_code = getattr(response, "status", 200)
                success = 200 <= status_code < 300
                record["status"] = "sent" if success else "error"
                record["status_code"] = status_code
                self._append_log(record)
                if success:
                    self._append_analytics(content)
                return success
        except urllib.error.HTTPError as exc:
            record["status"] = "error"
            record["status_code"] = exc.code
            self._append_log(record)
            logger.error("Bybit Square API error %s", exc.code)
        except Exception as exc:
            record["status"] = "error"
            record["reason"] = str(exc)
            self._append_log(record)
            logger.error("Bybit Square publish failed: %s", exc)
        return False

    def _append_log(self, record: dict[str, Any]) -> bool:
        try:
            with open(self.storage_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")
            return True
        except Exception as exc:
            logger.error("Failed to write Bybit log: %s", exc)
            return False

    def _append_analytics(self, content: str) -> bool:
        cashtags = [part for part in content.split() if part.startswith("$")]
        analytics = {
            "ts": datetime.now(UTC).isoformat(),
            "platform": "bybit_square",
            "char_count": len(content),
            "cashtags": cashtags,
            "estimated_views": 90 + (20 * len(cashtags)),
            "engagement_estimate": round(0.7 + (0.12 * len(cashtags)), 2),
        }
        try:
            with open(self.analytics_file, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(analytics, default=str) + "\n")
            return True
        except Exception as exc:
            logger.error("Failed to write Bybit analytics: %s", exc)
            return False
