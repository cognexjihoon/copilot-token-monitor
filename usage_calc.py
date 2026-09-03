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
    EXCEEDED = "exceeded"  # 초과


STATUS_LABEL = {
    Status.MARGIN: "여유",
    Status.ON_TRACK: "적정",
    Status.WARNING: "주의",
    Status.EXCEEDED: "초과",
}

STATUS_COLOR = {
    Status.MARGIN: "#2ecc71",
    Status.ON_TRACK: "#3498db",
    Status.WARNING: "#f1c40f",
    Status.EXCEEDED: "#e74c3c",
}

# pace_ratio thresholds: at/below MARGIN is comfortably behind the ideal
# pace, between MARGIN and WARNING is on track, above WARNING is ahead of
# the ideal pace.
PACE_MARGIN_THRESHOLD = 0.80
PACE_WARNING_THRESHOLD = 1.05


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
