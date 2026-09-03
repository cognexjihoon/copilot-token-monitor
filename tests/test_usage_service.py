from datetime import date

import pytest

import usage_cache
import usage_service
from config import AppConfig
from scrape_client import ScrapeError, ScrapedQuota
from usage_service import UsageService


def _point_cache_at(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_cache, "CACHE_PATH", tmp_path / "usage_cache.json")
    monkeypatch.setattr(usage_cache, "APP_DIR", tmp_path)


def test_refresh_rejects_invalid_config(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    service = UsageService(AppConfig())  # no cookie set -> invalid
    with pytest.raises(ScrapeError):
        service.refresh()


def test_refresh_builds_snapshot_from_scrape(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    fixed_today = date(2026, 9, 3)  # Thursday
    monkeypatch.setattr(usage_service, "date", _FixedDate(fixed_today))
    monkeypatch.setattr(
        usage_service, "fetch_quota", lambda cookie: ScrapedQuota(used=2595.0, quota=20000.0)
    )

    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    service = UsageService(cfg)

    result = service.refresh()

    assert result.snapshot.used == 2595.0
    assert result.snapshot.quota == 20000.0
    assert result.warnings == []
    assert result.daily_series == [(fixed_today, 2595.0)]


def test_refresh_falls_back_to_manual_quota_when_scrape_quota_missing(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    monkeypatch.setattr(usage_service, "date", _FixedDate(date(2026, 9, 3)))
    monkeypatch.setattr(
        usage_service, "fetch_quota", lambda cookie: ScrapedQuota(used=500.0, quota=0.0)
    )

    cfg = AppConfig(monthly_quota=12345.0)
    cfg.set_cookie("user_session=abc")
    service = UsageService(cfg)

    result = service.refresh()

    assert result.snapshot.quota == 12345.0
    assert len(result.warnings) == 1
    assert "12345" in result.warnings[0] or "12,345" in result.warnings[0]


def test_refresh_propagates_scrape_error(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)

    def _raise(cookie):
        raise ScrapeError("세션 만료")

    monkeypatch.setattr(usage_service, "fetch_quota", _raise)

    cfg = AppConfig()
    cfg.set_cookie("user_session=expired")
    service = UsageService(cfg)

    with pytest.raises(ScrapeError):
        service.refresh()


def test_update_daily_cache_computes_deltas_from_cumulative_readings(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    service = UsageService(cfg)

    # seed prior days as cumulative month-to-date readings
    usage_cache.save_cache({"2026-09-01": 100.0, "2026-09-02": 250.0})

    series = service._update_daily_cache(2026, 9, date(2026, 9, 3), used_month_to_date=400.0)

    assert series == [
        (date(2026, 9, 1), 100.0),
        (date(2026, 9, 2), 150.0),
        (date(2026, 9, 3), 150.0),
    ]


def test_update_daily_cache_overwrites_todays_entry_on_rerun(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    service = UsageService(cfg)

    usage_cache.save_cache({"2026-09-01": 100.0})
    service._update_daily_cache(2026, 9, date(2026, 9, 1), used_month_to_date=120.0)
    series = service._update_daily_cache(2026, 9, date(2026, 9, 1), used_month_to_date=150.0)

    assert series == [(date(2026, 9, 1), 150.0)]
    assert usage_cache.load_cache() == {"2026-09-01": 150.0}


def test_update_daily_cache_ignores_other_months(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    service = UsageService(cfg)

    usage_cache.save_cache({"2026-08-31": 999.0})
    series = service._update_daily_cache(2026, 9, date(2026, 9, 1), used_month_to_date=10.0)

    assert series == [(date(2026, 9, 1), 10.0)]


class _FixedDate:
    """Stand-in for the `date` class that makes `date.today()` deterministic
    while leaving `date(...)` construction and comparisons intact."""

    def __init__(self, fixed_today: date):
        self._fixed_today = fixed_today

    def __call__(self, *args, **kwargs):
        return date(*args, **kwargs)

    def today(self):
        return self._fixed_today

    def fromisoformat(self, s):
        return date.fromisoformat(s)
