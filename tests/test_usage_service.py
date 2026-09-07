from datetime import date

import pytest

import config
import usage_cache
import usage_service
from config import AppConfig
from scrape_client import ScrapeError, ScrapedQuota
from usage_service import UsageService


def _point_cache_at(tmp_path, monkeypatch):
    monkeypatch.setattr(usage_cache, "CACHE_PATH", tmp_path / "usage_cache.json")
    monkeypatch.setattr(usage_cache, "APP_DIR", tmp_path)
    # UsageService._maybe_notify_teams calls cfg.save() when it notifies -
    # point config persistence at tmp_path too so that doesn't touch the
    # real (or another test's) config.json.
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(config, "APP_DIR", tmp_path)


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


def test_refresh_uses_scraped_quota_even_when_zero(tmp_path, monkeypatch):
    # there's no manual fallback anymore -- whatever the scrape reports is
    # used as-is, including the (unlikely) edge case of a zero quota; the
    # zero-quota guard lives in UsageSnapshot.usage_pct, not here.
    _point_cache_at(tmp_path, monkeypatch)
    monkeypatch.setattr(usage_service, "date", _FixedDate(date(2026, 9, 3)))
    monkeypatch.setattr(
        usage_service, "fetch_quota", lambda cookie: ScrapedQuota(used=500.0, quota=0.0)
    )

    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    service = UsageService(cfg)

    result = service.refresh()

    assert result.snapshot.quota == 0.0
    assert result.warnings == []


def test_refresh_propagates_scrape_error(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)

    def _raise(cookie):
        raise ScrapeError("세션 만료", retryable=False)

    monkeypatch.setattr(usage_service, "fetch_quota", _raise)

    cfg = AppConfig()
    cfg.set_cookie("user_session=expired")
    service = UsageService(cfg)

    with pytest.raises(ScrapeError):
        service.refresh()


def test_refresh_does_not_retry_non_retryable_errors(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    calls = []

    def _raise(cookie):
        calls.append(cookie)
        raise ScrapeError("세션 만료", retryable=False)

    monkeypatch.setattr(usage_service, "fetch_quota", _raise)

    cfg = AppConfig()
    cfg.set_cookie("user_session=expired")
    service = UsageService(cfg, retry_delay_sec=0)

    with pytest.raises(ScrapeError):
        service.refresh()

    assert len(calls) == 1  # no retries for a failure that retrying can't fix


def test_refresh_retries_transient_errors_then_succeeds(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    monkeypatch.setattr(usage_service, "date", _FixedDate(date(2026, 9, 3)))
    calls = []

    def _flaky(cookie):
        calls.append(cookie)
        if len(calls) < 3:
            raise ScrapeError("일시적 오류")  # retryable by default
        return ScrapedQuota(used=100.0, quota=1000.0)

    monkeypatch.setattr(usage_service, "fetch_quota", _flaky)

    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    service = UsageService(cfg, retry_delay_sec=0)

    result = service.refresh()

    assert len(calls) == 3
    assert result.snapshot.used == 100.0


def test_refresh_gives_up_after_max_retries(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    calls = []

    def _always_fails(cookie):
        calls.append(cookie)
        raise ScrapeError("계속 실패")  # retryable by default

    monkeypatch.setattr(usage_service, "fetch_quota", _always_fails)

    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    service = UsageService(cfg, retry_delay_sec=0)

    with pytest.raises(ScrapeError):
        service.refresh()

    assert len(calls) == usage_service.MAX_FETCH_RETRIES + 1


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


def test_maybe_notify_teams_skips_when_no_webhook_configured(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(usage_service, "send_teams_message", lambda *a, **k: calls.append(a))

    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    service = UsageService(cfg)

    from usage_calc import UsageSnapshot

    service._maybe_notify_teams(
        UsageSnapshot(used=900.0, quota=1000.0, elapsed_bdays=1, total_bdays=20), date(2026, 9, 3)
    )

    assert calls == []


def test_maybe_notify_teams_sends_once_when_over_threshold(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(usage_service, "send_teams_message", lambda *a, **k: calls.append(a))

    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    cfg.teams_webhook_url = "https://example.com/webhook"
    cfg.teams_threshold_pct = 80.0
    service = UsageService(cfg)

    from usage_calc import UsageSnapshot

    over = UsageSnapshot(used=900.0, quota=1000.0, elapsed_bdays=1, total_bdays=20)  # 90%
    service._maybe_notify_teams(over, date(2026, 9, 3))
    service._maybe_notify_teams(over, date(2026, 9, 4))  # same month, already notified

    assert len(calls) == 1
    assert cfg.teams_notified_month == "2026-09"


def test_maybe_notify_teams_rearms_after_dropping_below_threshold(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(usage_service, "send_teams_message", lambda *a, **k: calls.append(a))

    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    cfg.teams_webhook_url = "https://example.com/webhook"
    cfg.teams_threshold_pct = 80.0
    service = UsageService(cfg)

    from usage_calc import UsageSnapshot

    over = UsageSnapshot(used=900.0, quota=1000.0, elapsed_bdays=1, total_bdays=20)  # 90%
    under = UsageSnapshot(used=500.0, quota=1000.0, elapsed_bdays=1, total_bdays=20)  # 50%

    service._maybe_notify_teams(over, date(2026, 9, 3))
    service._maybe_notify_teams(under, date(2026, 9, 10))  # quota bumped, drops back below
    service._maybe_notify_teams(over, date(2026, 9, 15))  # crosses again -> notifies again

    assert len(calls) == 2
    assert cfg.teams_notified_month == "2026-09"


def test_maybe_notify_teams_swallows_send_failures(tmp_path, monkeypatch):
    _point_cache_at(tmp_path, monkeypatch)

    def _raise(*a, **k):
        raise usage_service.requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(usage_service, "send_teams_message", _raise)

    cfg = AppConfig()
    cfg.set_cookie("user_session=abc")
    cfg.teams_webhook_url = "https://example.com/webhook"
    cfg.teams_threshold_pct = 80.0
    service = UsageService(cfg)

    from usage_calc import UsageSnapshot

    over = UsageSnapshot(used=900.0, quota=1000.0, elapsed_bdays=1, total_bdays=20)
    service._maybe_notify_teams(over, date(2026, 9, 3))  # must not raise

    # the send failed, so the month must NOT be marked as notified -
    # otherwise a transient failure would permanently suppress the alert
    assert cfg.teams_notified_month == ""


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
