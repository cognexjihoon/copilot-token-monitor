"""Business-day pacing math and status/color classification."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from enum import Enum


def is_business_day(d: date) -> bool:
    return d.weekday() < 5  # Mon=0 .. Fri=4


def business_days_in_month(year: int, month: int) -> int:
    _, last_day = calendar.monthrange(year, month)
    return sum(1 for day in range(1, last_day + 1) if is_business_day(date(year, month, day)))


def elapsed_business_days(year: int, month: int, as_of: date) -> int:
    _, last_day = calendar.monthrange(year, month)
    end_day = min(as_of.day, last_day) if (as_of.year, as_of.month) == (year, month) else last_day
    return sum(1 for day in range(1, end_day + 1) if is_business_day(date(year, month, day)))


class Status(Enum):
    MARGIN = "margin"      # 여유
    ON_TRACK = "on_track"  # 적정
    WARNING = "warning"    # 주의
    DANGER = "danger"      # 위험 (페이스가 심하게 초과)
    CRITICAL = "critical"  # 임박 (쿼터 자체가 거의 소진)
    EXCEEDED = "exceeded"  # 초과 (쿼터 완전 소진)


STATUS_LABEL = {
    Status.MARGIN: "여유",
    Status.ON_TRACK: "적정",
    Status.WARNING: "주의",
    Status.DANGER: "위험",
    Status.CRITICAL: "임박",
    Status.EXCEEDED: "초과",
}

STATUS_COLOR = {
    Status.MARGIN: "#2ecc71",
    Status.ON_TRACK: "#3498db",
    # This is DetailWindow's color (labels/progress bar/chart use it
    # as-is) - full 100% saturation at ~51% lightness reads as a clean,
    # vivid gold rather than the muddy ochre a darker/duller value gave
    # (#D99B00 at ~42% lightness). Do NOT dial this down to fix tray
    # glare: the tray icon needs a lower saturation than the window does
    # to look right, so that adjustment belongs in icon_factory.py's
    # _tray_digit_color (which already relights lightness independently)
    # instead of here - tying both to one shared value just makes fixing
    # one break the other.
    Status.WARNING: "#FFC107",
    Status.DANGER: "#E67E22",
    Status.CRITICAL: "#E74C3C",
    # Solid black rather than a deeper red - EXCEEDED means the quota is
    # completely gone, a different (and final) kind of state from the
    # amber->orange->red "getting worse" ramp above it, so it breaks from
    # that ramp entirely instead of just being "the reddest red". Paired
    # with a skull tray icon (icon_factory.make_icon) instead of a tinted
    # digit for the same reason - see that module for why the tray icon
    # renders this one differently too (its usual relight-for-theme
    # treatment would turn a flat black into gray).
    Status.EXCEEDED: "#000000",
}

# pace_ratio thresholds: at/below MARGIN is comfortably behind the ideal
# pace, between MARGIN and WARNING is on track, between WARNING and
# DANGER is moderately ahead, above DANGER is severely ahead.
PACE_MARGIN_THRESHOLD = 0.80
PACE_WARNING_THRESHOLD = 1.05
PACE_DANGER_THRESHOLD = 1.20
# Absolute-usage threshold, independent of pace: CRITICAL fires once the
# quota itself is nearly gone even if pace still looks fine (e.g. late in
# the month, when expected_used has caught up to actual usage) - pace
# alone wouldn't otherwise warn that there's almost nothing left.
USAGE_CRITICAL_PCT = 90.0


@dataclass
class UsageSnapshot:
    used: float
    quota: float
    elapsed_bdays: int
    total_bdays: int

    @property
    def usage_pct(self) -> float:
        return (self.used / self.quota * 100) if self.quota > 0 else 0.0

    @property
    def expected_used(self) -> float:
        if self.total_bdays <= 0:
            return 0.0
        return self.quota * (self.elapsed_bdays / self.total_bdays)

    @property
    def pace_ratio(self) -> float:
        expected = self.expected_used
        if expected <= 0:
            return float("inf") if self.used > 0 else 0.0
        return self.used / expected

    @property
    def status(self) -> Status:
        if self.quota > 0 and self.used >= self.quota:
            return Status.EXCEEDED
        if self.quota > 0 and self.usage_pct >= USAGE_CRITICAL_PCT:
            return Status.CRITICAL
        if self.pace_ratio > PACE_DANGER_THRESHOLD:
            return Status.DANGER
        if self.pace_ratio <= PACE_MARGIN_THRESHOLD:
            return Status.MARGIN
        if self.pace_ratio <= PACE_WARNING_THRESHOLD:
            return Status.ON_TRACK
        return Status.WARNING

    @property
    def color(self) -> str:
        return STATUS_COLOR[self.status]

    @property
    def label(self) -> str:
        return STATUS_LABEL[self.status]
