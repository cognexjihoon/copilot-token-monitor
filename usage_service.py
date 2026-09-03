"""Ties together the billing-page scraper and the local daily cache to
produce one refreshed snapshot + trend series per poll.

GitHub's billing REST API requires the token holder to be an organization
admin/owner to read another member's usage, which most users are not. So
usage and quota are both obtained by scraping the rendered
github.com/settings/billing page using the user's own session cookie
(see scrape_client.py) - the same numbers the user would see by hand,
just automated. `monthly_quota` in config is only a fallback used when the
scrape fails to parse a quota value.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Tuple

from config import AppConfig
from scrape_client import ScrapeError, fetch_quota
from usage_calc import UsageSnapshot, business_days_in_month, elapsed_business_days
from usage_cache import load_cache, save_cache, set_day


@dataclass
class RefreshResult:
    snapshot: UsageSnapshot
    daily_series: List[Tuple[date, float]]
    last_updated: datetime
    warnings: List[str] = field(default_factory=list)


class UsageService:
    def __init__(self, config: AppConfig):
        self.config = config

    def refresh(self) -> RefreshResult:
        cfg = self.config
        if not cfg.is_valid():
            raise ScrapeError("설정이 완료되지 않았습니다. 설정 창에서 GitHub 로그인을 진행하세요.")

        today = date.today()
        year, month = today.year, today.month
        warnings: List[str] = []

        scraped = fetch_quota(cfg.cookie())
        used = scraped.used
        quota = scraped.quota if scraped.quota > 0 else cfg.monthly_quota
        if scraped.quota <= 0:
            warnings.append(f"페이지에서 쿼터를 읽지 못해 저장된 값({cfg.monthly_quota:g})을 사용합니다.")

        total_bdays = business_days_in_month(year, month)
        elapsed_bdays = elapsed_business_days(year, month, today)
        snapshot = UsageSnapshot(used=used, quota=quota, elapsed_bdays=elapsed_bdays, total_bdays=total_bdays)

        daily_series = self._update_daily_cache(year, month, today, used)

        return RefreshResult(
            snapshot=snapshot,
            daily_series=daily_series,
            last_updated=datetime.now(),
            warnings=warnings,
        )

    def _update_daily_cache(
        self, year: int, month: int, today: date, used_month_to_date: float
    ) -> List[Tuple[date, float]]:
        """The scraper only reports a cumulative month-to-date total (no
        per-day breakdown), so today's cumulative reading is cached and the
        per-day trend is derived as the delta between consecutive cached
        cumulative readings within the month."""
        cache = load_cache()
        set_day(cache, today.isoformat(), used_month_to_date)
        save_cache(cache)

        prefix = f"{year:04d}-{month:02d}-"
        month_days = sorted(
            (iso, value) for iso, value in cache.items() if iso.startswith(prefix)
        )

        series: List[Tuple[date, float]] = []
        previous_cumulative = 0.0
        for iso, cumulative in month_days:
            series.append((date.fromisoformat(iso), cumulative - previous_cumulative))
            previous_cumulative = cumulative
        return series
