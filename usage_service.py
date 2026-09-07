"""Ties together the billing-page scraper and the local daily cache to
produce one refreshed snapshot + trend series per poll.

GitHub's billing REST API requires the token holder to be an organization
admin/owner to read another member's usage, which most users are not. So
usage and quota are both obtained by scraping a rendered GitHub page using
the user's own session cookie (see scrape_client.py) - the same numbers
the user would see by hand, just automated.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Tuple

import requests

from config import AppConfig
from scrape_client import ScrapeError, ScrapedQuota, fetch_quota
from teams_notifier import send_teams_message
from usage_calc import UsageSnapshot, business_days_in_month, elapsed_business_days
from usage_cache import load_cache, save_cache, set_day

# One initial attempt plus up to this many retries for a *retryable*
# ScrapeError (network blip, half-rendered page, transient 5xx) - a
# non-retryable one (expired/missing session) is never worth retrying and
# is raised straight away instead, see ScrapeError.retryable.
MAX_FETCH_RETRIES = 3
RETRY_DELAY_SEC = 2.0


@dataclass
class RefreshResult:
    snapshot: UsageSnapshot
    daily_series: List[Tuple[date, float]]
    last_updated: datetime
    warnings: List[str] = field(default_factory=list)


class UsageService:
    def __init__(self, config: AppConfig, *, retry_delay_sec: float = RETRY_DELAY_SEC):
        self.config = config
        self._retry_delay_sec = retry_delay_sec

    def refresh(self) -> RefreshResult:
        cfg = self.config
        if not cfg.is_valid():
            raise ScrapeError("설정이 완료되지 않았습니다. 설정 창에서 GitHub 로그인을 진행하세요.", retryable=False)

        today = date.today()
        year, month = today.year, today.month
        warnings: List[str] = []

        scraped = self._fetch_quota_with_retry(cfg.cookie())
        used = scraped.used
        quota = scraped.quota

        total_bdays = business_days_in_month(year, month)
        elapsed_bdays = elapsed_business_days(year, month, today)
        snapshot = UsageSnapshot(used=used, quota=quota, elapsed_bdays=elapsed_bdays, total_bdays=total_bdays)

        daily_series = self._update_daily_cache(year, month, today, used)
        self._maybe_notify_teams(snapshot, today)

        return RefreshResult(
            snapshot=snapshot,
            daily_series=daily_series,
            last_updated=datetime.now(),
            warnings=warnings,
        )

    def _fetch_quota_with_retry(self, cookie: str) -> ScrapedQuota:
        attempts = MAX_FETCH_RETRIES + 1
        for attempt in range(1, attempts + 1):
            try:
                return fetch_quota(cookie)
            except ScrapeError as exc:
                if not exc.retryable or attempt == attempts:
                    raise
                time.sleep(self._retry_delay_sec)
        raise AssertionError("unreachable")  # loop always returns or raises

    def _maybe_notify_teams(self, snapshot: UsageSnapshot, today: date) -> None:
        """Sends a one-time-per-month Teams notification once usage crosses
        the configured threshold. Fires at most once per calendar month
        (tracked via cfg.teams_notified_month, persisted so a restart
        doesn't re-notify) rather than on every poll while still over the
        threshold; re-arms itself if usage ever dips back below it (e.g.
        the org bumped the quota) so a later re-crossing notifies again.
        A send failure is swallowed - a notification hiccup must never
        break the refresh itself."""
        cfg = self.config
        if not cfg.teams_webhook_url:
            return

        month_key = f"{today.year:04d}-{today.month:02d}"
        if snapshot.usage_pct < cfg.teams_threshold_pct:
            if cfg.teams_notified_month:
                cfg.teams_notified_month = ""
                cfg.save()
            return

        if cfg.teams_notified_month == month_key:
            return

        try:
            send_teams_message(
                cfg.teams_webhook_url,
                "⚠ Copilot 사용량 경고",
                f"사용량이 {snapshot.usage_pct:.1f}%로 임계치({cfg.teams_threshold_pct:.0f}%)를 초과했습니다.\n"
                f"{snapshot.used:,.0f} / {snapshot.quota:,.0f} credits",
            )
        except requests.RequestException:
            return

        cfg.teams_notified_month = month_key
        cfg.save()

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
