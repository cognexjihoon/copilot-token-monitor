"""Local JSON cache of daily usage totals, keyed by ISO date, so the trend
chart doesn't need to re-fetch every past business day on every poll."""
from __future__ import annotations

import json
from typing import Dict

from config import CACHE_PATH, APP_DIR


def load_cache() -> Dict[str, float]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(data: Dict[str, float]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def set_day(cache: Dict[str, float], iso_date: str, value: float) -> None:
    cache[iso_date] = value
