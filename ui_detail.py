from __future__ import annotations

import sys
from datetime import date

import matplotlib

matplotlib.use("QtAgg")
# DejaVu Sans (matplotlib's default) has no Hangul glyphs and silently
# renders them as tofu boxes, so pick the font each OS actually ships with
# Korean coverage. Listing all three unconditionally made matplotlib log a
# "not found" warning per platform-inappropriate name (e.g. AppleGothic on
# Windows, Malgun Gothic on macOS).
if sys.platform == "win32":
    _korean_font = "Malgun Gothic"
elif sys.platform == "darwin":
    _korean_font = "Apple SD Gothic Neo"
else:
    _korean_font = "NanumGothic"
matplotlib.rcParams["font.family"] = [_korean_font, "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from usage_calc import business_days_in_month
from usage_service import RefreshResult


class DetailWindow(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Copilot 사용량 상세")
        self.setMinimumSize(560, 480)

        self.pct_label = QLabel("--")
        self.pct_label.setAlignment(Qt.AlignCenter)
        self.pct_label.setStyleSheet("font-size: 40px; font-weight: bold;")

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px;")

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(True)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)

        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #b8860b;")

        self.updated_label = QLabel("")
        self.updated_label.setStyleSheet("color: gray; font-size: 11px;")

        self.figure = Figure(figsize=(5, 3))
        self.canvas = FigureCanvasQTAgg(self.figure)

        refresh_btn = QPushButton("지금 새로고침")
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        self._on_refresh_requested = None

        top_row = QHBoxLayout()
        top_row.addStretch(1)
        top_row.addWidget(refresh_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.pct_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        layout.addWidget(self.detail_label)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self.updated_label)

    def set_refresh_callback(self, callback) -> None:
        self._on_refresh_requested = callback

    def _on_refresh_clicked(self) -> None:
        if self._on_refresh_requested:
            self._on_refresh_requested()

    def show_error(self, message: str) -> None:
        self.status_label.setText("오류")
        self.detail_label.setText(message)

    def update_result(self, result: RefreshResult) -> None:
        snap = result.snapshot
        self.pct_label.setText(f"{snap.usage_pct:.1f}%")
        self.pct_label.setStyleSheet(f"font-size: 40px; font-weight: bold; color: {snap.color};")
        self.status_label.setText(f"상태: {snap.label}")
        self.progress.setValue(int(min(snap.usage_pct, 100)))
        self.progress.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {snap.color}; }}"
        )
        self.detail_label.setText(
            f"사용량: {snap.used:,.0f} / {snap.quota:,.0f} credits\n"
            f"영업일 진행: {snap.elapsed_bdays} / {snap.total_bdays}일 "
            f"({(snap.elapsed_bdays / snap.total_bdays * 100 if snap.total_bdays else 0):.1f}%)\n"
            f"페이스 대비: {snap.pace_ratio * 100:.0f}% (100%보다 크면 예상 소진 속도보다 빠름)"
        )
        self.warning_label.setText("\n".join(result.warnings))
        self.updated_label.setText(f"마지막 업데이트: {result.last_updated.strftime('%Y-%m-%d %H:%M:%S')}")
        self._draw_chart(result)

    def _draw_chart(self, result: RefreshResult) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        snap = result.snapshot
        series = result.daily_series
        if not series:
            self.canvas.draw()
            return

        today = date.today()
        total_bdays = business_days_in_month(today.year, today.month)

        cumulative = []
        running = 0.0
        for _, value in series:
            running += value
            cumulative.append(running)

        xs = list(range(1, len(series) + 1))
        ax.bar(xs, [v for _, v in series], color="#95a5a6", alpha=0.5, label="일별 사용량")
        ax.plot(xs, cumulative, color=snap.color, marker="o", linewidth=2, label="누적 사용량")

        if total_bdays > 0 and snap.quota > 0:
            pace_xs = [1, total_bdays]
            pace_ys = [snap.quota / total_bdays, snap.quota]
            ax.plot(pace_xs, pace_ys, color="#7f8c8d", linestyle="--", label="이상적 페이스")

        ax.set_xlabel("영업일 경과")
        ax.set_ylabel("credits")
        ax.legend(loc="upper left", fontsize=8)
        self.figure.tight_layout()
        self.canvas.draw()
