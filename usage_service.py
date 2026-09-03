"""Ties together the billing API, the optional quota scraper, and the local
daily cache to produce one refreshed snapshot + trend series per poll."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Tuple

from config import AppConfig
from github_client import CopilotUsageClient, GitHubApiError
from scrape_client import ScrapeError, fetch_quota
from usage_calc import UsageSnapshot, business_days_in_month, elapsed_business_days, is_business_day
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
            raise GitHubApiError("설정이 완료되지 않았습니다. 설정 창에서 토큰/사용자명을 입력하세요.")

        client = CopilotUsageClient(
            token=cfg.token(),
            username=cfg.username,
            org=cfg.org,
            auth_mode=cfg.auth_mode,
            endpoint_kind=cfg.endpoint_kind,
        )

        today = date.today()
        year, month = today.year, today.month
        warnings: List[str] = []

        month_result = client.get_month_total(year, month)
        used = month_result.net_quantity

        quota = cfg.monthly_quota
        if cfg.quota_source == "budget_api":
            if cfg.enterprise:
                try:
                    quota = client.get_budget_amount(cfg.enterprise)
                except GitHubApiError as exc:
                    warnings.append(f"Budget API 조회 실패, 마지막 저장값({cfg.monthly_quota:g}) 사용: {exc}")
            else:
                warnings.append("Budget API 사용이 켜져 있지만 엔터프라이즈명이 없습니다. 설정에서 입력하세요.")
        elif cfg.quota_source == "scrape":
            if cfg.cookie():
                try:
                    scraped = fetch_quota(cfg.cookie())
                    quota = scraped.quota
                except ScrapeError as exc:
                    warnings.append(f"쿼터 자동 감지 실패, 마지막 저장값({cfg.monthly_quota:g}) 사용: {exc}")
            else:
                warnings.append("쿼터 자동 감지가 켜져 있지만 세션 쿠키가 없습니다. 설정에서 입력하세요.")

        total_bdays = business_days_in_month(year, month)
        elapsed_bdays = elapsed_business_days(year, month, today)
        snapshot = UsageSnapshot(used=used, quota=quota, elapsed_bdays=elapsed_bdays, total_bdays=total_bdays)

        daily_series = self._refresh_daily_series(client, year, month, today, warnings)

        return RefreshResult(
            snapshot=snapshot,
            daily_series=daily_series,
            last_updated=datetime.now(),
            warnings=warnings,
        )

    def _refresh_daily_series(
        self, client: CopilotUsageClient, year: int, month: int, today: date, warnings: List[str]
    ) -> List[Tuple[date, float]]:
        cache = load_cache()
        for day in range(1, today.day + 1):
            d = date(year, month, day)
            if not is_business_day(d):
                continue
            iso = d.isoformat()
            if iso in cache and day != today.day:
                continue  # past days don't change once cached; today is always refetched
            try:
                result = client.get_day_total(year, month, day)
                set_day(cache, iso, result.net_quantity)
            except GitHubApiError as exc:
                if iso not in cache:
                    warnings.append(f"{iso} 사용량 조회 실패: {exc}")
        save_cache(cache)

        prefix = f"{year:04d}-{month:02d}-"
        series = [
            (date.fromisoformat(iso), value) for iso, value in cache.items() if iso.startswith(prefix)
        ]
        series.sort(key=lambda pair: pair[0])
        return series
