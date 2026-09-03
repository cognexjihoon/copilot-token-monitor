from datetime import date

import pytest

from usage_calc import (
    Status,
    UsageSnapshot,
    business_days_in_month,
    elapsed_business_days,
    is_business_day,
)


def test_is_business_day():
    assert is_business_day(date(2026, 9, 7))  # Monday
    assert is_business_day(date(2026, 9, 11))  # Friday
    assert not is_business_day(date(2026, 9, 12))  # Saturday
    assert not is_business_day(date(2026, 9, 13))  # Sunday


def test_business_days_in_month_september_2026():
    # Sept 2026: Tue 1 .. Wed 30, 4 full weekends inside -> 22 business days
    assert business_days_in_month(2026, 9) == 22


def test_business_days_in_month_february_leap_year():
    # Feb 2028 is a leap year (29 days), starts on a Tuesday
    assert business_days_in_month(2028, 2) == 21


def test_elapsed_business_days_mid_month():
    # Sept 2026: as_of = Fri 2026-09-11 (day 11) -> business days 1..11
    assert elapsed_business_days(2026, 9, date(2026, 9, 11)) == 9


def test_elapsed_business_days_clamps_to_month_end_for_other_month():
    # as_of belongs to a different month/year -> counts the whole month
    assert elapsed_business_days(2026, 9, date(2026, 10, 5)) == business_days_in_month(2026, 9)


def test_elapsed_business_days_on_weekend_still_counts_prior_weekdays():
    # Sat 2026-09-12: days 1..12 elapsed, of which day 12 itself is not a business day
    assert elapsed_business_days(2026, 9, date(2026, 9, 12)) == elapsed_business_days(
        2026, 9, date(2026, 9, 11)
    )


@pytest.mark.parametrize(
    "used,quota,elapsed,total,expected_pct",
    [
        (1000, 20000, 10, 20, 5.0),
        (0, 20000, 0, 20, 0.0),
        (100, 0, 5, 20, 0.0),  # zero quota must not raise ZeroDivisionError
    ],
)
def test_usage_pct(used, quota, elapsed, total, expected_pct):
    snap = UsageSnapshot(used=used, quota=quota, elapsed_bdays=elapsed, total_bdays=total)
    assert snap.usage_pct == pytest.approx(expected_pct)


def test_expected_used_scales_with_elapsed_fraction():
    snap = UsageSnapshot(used=0, quota=20000, elapsed_bdays=10, total_bdays=20)
    assert snap.expected_used == pytest.approx(10000.0)


def test_expected_used_zero_total_bdays_is_zero():
    snap = UsageSnapshot(used=0, quota=20000, elapsed_bdays=0, total_bdays=0)
    assert snap.expected_used == 0.0


def test_pace_ratio_no_usage_yet_and_no_expectation_is_zero():
    snap = UsageSnapshot(used=0, quota=20000, elapsed_bdays=0, total_bdays=20)
    assert snap.pace_ratio == 0.0


def test_pace_ratio_used_before_any_expected_is_infinite():
    snap = UsageSnapshot(used=5, quota=20000, elapsed_bdays=0, total_bdays=20)
    assert snap.pace_ratio == float("inf")


def test_pace_ratio_on_pace():
    snap = UsageSnapshot(used=5000, quota=20000, elapsed_bdays=10, total_bdays=20)
    assert snap.pace_ratio == pytest.approx(0.5)


def test_status_margin_at_or_below_80pct_of_pace():
    # expected = 10000, used = 8000 -> ratio 0.80 <= 0.80 margin threshold
    snap = UsageSnapshot(used=8000, quota=20000, elapsed_bdays=10, total_bdays=20)
    assert snap.status == Status.MARGIN
    assert snap.color == "#2ecc71"
    assert snap.label == "여유"


def test_status_on_track_between_80_and_100pct_of_pace():
    # expected = 10000, used = 9500 -> ratio 0.95, between margin and warning
    snap = UsageSnapshot(used=9500, quota=20000, elapsed_bdays=10, total_bdays=20)
    assert snap.status == Status.ON_TRACK
    assert snap.color == "#3498db"
    assert snap.label == "적정"


def test_status_on_track_at_exactly_100pct_of_pace():
    snap = UsageSnapshot(used=10000, quota=20000, elapsed_bdays=10, total_bdays=20)
    assert snap.status == Status.ON_TRACK


def test_status_on_track_within_105pct_warning_buffer():
    # expected = 10000, used = 10400 -> ratio 1.04 <= 1.05 warning threshold
    snap = UsageSnapshot(used=10400, quota=20000, elapsed_bdays=10, total_bdays=20)
    assert snap.status == Status.ON_TRACK


def test_status_warning_above_105pct_of_pace():
    # expected = 10000, used = 10600 -> ratio 1.06, ahead of the 105% buffer
    snap = UsageSnapshot(used=10600, quota=20000, elapsed_bdays=10, total_bdays=20)
    assert snap.status == Status.WARNING
    assert snap.label == "주의"


def test_status_exceeded_takes_priority_over_pace():
    snap = UsageSnapshot(used=20000, quota=20000, elapsed_bdays=1, total_bdays=20)
    assert snap.status == Status.EXCEEDED
    assert snap.label == "초과"


def test_status_exceeded_when_used_over_quota_even_early_in_month():
    snap = UsageSnapshot(used=25000, quota=20000, elapsed_bdays=1, total_bdays=20)
    assert snap.status == Status.EXCEEDED
