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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from usage_calc import business_days_in_month, elapsed_business_days
from usage_service import RefreshResult

# Windows virtual desktops don't hide a window that's parked on an
# inactive one - Qt's isVisible() still reports True - they "cloak" it via
# DWM instead (DWMWA_CLOAKED), leaving its backing store/HDC in a state
# that isn't safe to paint into. Redrawing the matplotlib canvas against a
# cloaked window (e.g. a periodic background refresh firing while the
# detail window sits on a desktop the user has switched away from) has
# been observed to hard-crash the process, so callers must check
# is_effectively_visible() - not isVisible() - before pushing a repaint.
if sys.platform == "win32":
    import ctypes

    _DWMWA_CLOAKED = 14

    def _is_cloaked(hwnd: int) -> bool:
        cloaked = ctypes.c_int(0)
        try:
            result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(_DWMWA_CLOAKED),
                ctypes.byref(cloaked),
                ctypes.sizeof(cloaked),
            )
        except OSError:
            return False
        return result == 0 and cloaked.value != 0

else:

    def _is_cloaked(hwnd: int) -> bool:  # pragma: no cover - non-Windows
        return False


class PercentProgressBar(QProgressBar):
    """Draws the "N%" label centered within the filled chunk only, instead
    of Qt's default of centering it across the whole (mostly empty at low
    values) bar.

    Two earlier versions did this by hand-painting the label inside a
    custom paintEvent - first via style().drawControl(CE_ProgressBar,...)
    plus text in one QPainter session, then via super().paintEvent()
    followed by a second QPainter session for just the text - and both
    crashed on Windows with "recursive repaint detected" / "QBackingStore
    ::endPaint() called with active painter". Windows' native (Vista)
    style drives the progress chunk with its own internal QStyleAnimation
    timer, and *any* extra hand-rolled painting inside this widget's own
    paintEvent - even one that lets super() draw the chunk first - can
    still race with that timer's own repaint.

    This version never touches paintEvent at all: the label is a real
    child widget, repositioned/resized to match the chunk's current
    geometry whenever the value or the bar's own size changes. Both the
    native chunk and this label are then painted through Qt's ordinary,
    animation-safe widget compositing instead of anything we drive by
    hand, so there is nothing left to race with that timer.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTextVisible(False)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("color: black; background: transparent;")
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.valueChanged.connect(self._sync_label)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_label()

    def _sync_label(self, *_args) -> None:
        span = max(1, self.maximum() - self.minimum())
        chunk_width = round(self.width() * (self.value() - self.minimum()) / span)
        self._label.setGeometry(0, 0, chunk_width, self.height())
        self._label.setText(f"{self.value()}%" if chunk_width > 0 else "")


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

        self.progress = PercentProgressBar()
        self.progress.setRange(0, 100)

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

        self._last_result: RefreshResult | None = None
        self._was_cloaked = False
        # Cheap poll instead of relying on Qt show/hide events: DWM
        # cloaking a window when the user switches virtual desktops away
        # from it (and un-cloaking it on switching back) doesn't fire a
        # normal QShowEvent/QHideEvent, so a transition would otherwise go
        # unnoticed and the chart would stay stale until the next timed
        # refresh happens to land while this window is back in view.
        self._visibility_timer = QTimer(self)
        self._visibility_timer.setInterval(10000)
        self._visibility_timer.timeout.connect(self._check_visibility_transition)
        self._visibility_timer.start()

    def is_effectively_visible(self) -> bool:
        """True only if this window is both Qt-visible and actually being
        composited on some screen right now - see the module-level
        _is_cloaked() docstring for why isVisible() alone isn't enough."""
        if not self.isVisible():
            return False
        try:
            return not _is_cloaked(int(self.winId()))
        except Exception:
            return True

    def _check_visibility_transition(self) -> None:
        cloaked = self.isVisible() and not self.is_effectively_visible()
        if self._was_cloaked and not cloaked and self._last_result is not None:
            self._render(self._last_result)
        self._was_cloaked = cloaked

    def set_refresh_callback(self, callback) -> None:
        self._on_refresh_requested = callback

    def _on_refresh_clicked(self) -> None:
        if self._on_refresh_requested:
            self._on_refresh_requested()

    def show_error(self, message: str) -> None:
        self.status_label.setText("오류")
        self.detail_label.setText(message)

    def update_result(self, result: RefreshResult) -> None:
        self._last_result = result
        if not self.is_effectively_visible():
            # Window is open but parked on an inactive virtual desktop
            # (cloaked) - skip repainting now; _check_visibility_transition
            # will render this cached result once it's back in view.
            return
        self._render(result)

    def _render(self, result: RefreshResult) -> None:
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
            f"페이스 대비: {snap.pace_ratio * 100:.0f}% (100%를 넘으면 오늘까지 써야 할 양보다 더 많이 쓴 것)"
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

        # x must be each entry's actual elapsed-business-day-of-month, not
        # its position in the (possibly gapped, e.g. app not open every
        # day) cache list -- otherwise this drifts left of where the ideal
        # pace line expects it, making cumulative usage look far ahead of
        # pace even when it's only marginally so.
        xs = [elapsed_business_days(d.year, d.month, d) for d, _ in series]
        ax.bar(xs, [v for _, v in series], color="#95a5a6", alpha=0.5, label="일별 사용량", width=0.6)
        ax.plot(xs, cumulative, color=snap.color, marker="o", linewidth=2, label="누적 사용량")

        if total_bdays > 0 and snap.quota > 0:
            pace_xs = [0, total_bdays]
            pace_ys = [0, snap.quota]
            ax.plot(pace_xs, pace_ys, color="#7f8c8d", linestyle="--", label="이상적 페이스")

        ax.set_xlabel("영업일 경과")
        ax.set_ylabel("credits")
        ax.legend(loc="upper left", fontsize=8)
        self.figure.tight_layout()
        self.canvas.draw()
