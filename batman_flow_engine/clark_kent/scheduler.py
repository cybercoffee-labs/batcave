"""Scheduling logic for Clark Kent posting windows."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = MODULE_DIR / "storage"
PUBLISHED_FILE = STORAGE_DIR / "published.jsonl"


class PostScheduler:
    """Gate social posts to specific time windows and daily limits."""

    OPTIMAL_HOURS = [8, 12, 18, 21]
    MAX_POSTS_PER_DAY = 4
    WINDOW_LABELS = {
        8: "8:00-9:00",
        12: "12:00-13:00",
        18: "18:00-19:00",
        21: "21:00-22:00",
    }

    def __init__(self, storage_file: Path | None = None):
        self.storage_file = Path(storage_file) if storage_file else PUBLISHED_FILE

    def can_post_now(self) -> bool:
        current_hour = datetime.now().hour
        return current_hour in self.OPTIMAL_HOURS

    def posts_today(self) -> int:
        today = datetime.now().date()
        count = 0
        if not self.storage_file.exists():
            return 0

        with open(self.storage_file, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("status") not in {"ok", "sent"}:
                        continue
                    ts = record.get("ts")
                    if not ts:
                        continue
                    if datetime.fromisoformat(ts.replace("Z", "+00:00")).date() == today:
                        count += 1
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
        return count

    def next_optimal_hour(self) -> str:
        current_hour = datetime.now().hour
        for hour in self.OPTIMAL_HOURS:
            if current_hour < hour:
                return self.WINDOW_LABELS[hour]
        return f"tomorrow {self.WINDOW_LABELS[self.OPTIMAL_HOURS[0]]}"

    def can_post_today(self) -> bool:
        return self.posts_today() < self.MAX_POSTS_PER_DAY
