"""Entry point: system tray app that periodically checks GitHub Copilot
AI-credit usage against a monthly quota, paced by business days."""
from __future__ import annotations

import sys

import truststore

# Some corporate networks intercept TLS with a proxy whose root CA is
# installed in the OS trust store (so browsers/curl work) but not in the
# `certifi` bundle `requests` uses by default, causing SSL verification
# failures purely from that mismatch. Route `requests`/urllib3 through the
# OS trust store instead so it sees the same certs a real browser does.
truststore.inject_into_ssl()

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from config import AppConfig
from icon_factory import make_error_icon, make_icon
from scrape_client import ScrapeError
from ui_detail import DetailWindow
from ui_settings import SettingsDialog
from usage_service import RefreshResult, UsageService

# A refresh that's still "in flight" after this long is treated as stuck
# (e.g. a blocking network call spanning a sleep/wake cycle can wait far
# past its own requests.get(timeout=...) because the whole process - and
# the clock that timeout is measured against - was suspended too) rather
# than trusted to eventually finish on its own.
WATCHDOG_TIMEOUT_MS = 60_000


class RefreshWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service: UsageService):
        super().__init__()
        self.service = service

    def run(self) -> None:
        try:
            result = self.service.refresh()
        except ScrapeError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # unexpected errors must not silently kill the poll loop
            self.failed.emit(f"예상치 못한 오류: {exc}")
        else:
            self.succeeded.emit(result)


class TrayApp:
    def __init__(self, app: QApplication):
        self.app = app
        self.config = AppConfig.load()
        self.detail_window: DetailWindow | None = None
        self._thread: QThread | None = None
        self._worker: RefreshWorker | None = None
        self._refreshing = False
        self._watchdog: QTimer | None = None
        self._last_result: RefreshResult | None = None

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(make_error_icon())
        self.tray.setToolTip("Copilot 사용량 모니터 - 설정이 필요합니다")
        self.tray.activated.connect(self._on_tray_activated)

        self.status_action = QAction("상태: 확인 중...")
        self.status_action.setEnabled(False)

        menu = QMenu()
        menu.addAction(self.status_action)
        menu.addSeparator()
        detail_action = QAction("상세 보기", menu)
        detail_action.triggered.connect(self.open_detail_window)
        menu.addAction(detail_action)
        refresh_action = QAction("지금 새로고침", menu)
        refresh_action.triggered.connect(self.refresh_now)
        menu.addAction(refresh_action)
        settings_action = QAction("설정", menu)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)
        menu.addSeparator()
        quit_action = QAction("종료", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_now)
        self._apply_interval()

        if self.config.is_valid():
            self.refresh_now()
        else:
            self.open_settings()

    def _apply_interval(self) -> None:
        self.timer.start(self.config.poll_interval_min * 60 * 1000)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_detail_window()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config)
        if dialog.exec():
            self._apply_interval()
            self.refresh_now()

    def open_detail_window(self) -> None:
        if self.detail_window is None:
            self.detail_window = DetailWindow()
            self.detail_window.set_refresh_callback(self.refresh_now)
        if self._last_result is not None:
            self.detail_window.update_result(self._last_result)
        self.detail_window.show()
        self.detail_window.raise_()
        self.detail_window.activateWindow()

    def refresh_now(self) -> None:
        if not self.config.is_valid():
            self.tray.setToolTip("Copilot 사용량 모니터 - 설정이 필요합니다")
            self.status_action.setText("상태: 설정 필요")
            return
        if self._refreshing:
            return  # a refresh is already in flight

        self._refreshing = True
        service = UsageService(self.config)
        self._thread = QThread()
        self._worker = RefreshWorker(service)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self._on_refresh_succeeded)
        self._worker.failed.connect(self._on_refresh_failed)
        self._worker.succeeded.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()

        self._watchdog = QTimer()
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_refresh_watchdog_timeout)
        self._watchdog.start(WATCHDOG_TIMEOUT_MS)

    def _on_thread_finished(self) -> None:
        # _refreshing (not thread.isRunning()) is the in-flight guard so
        # refresh_now() never touches the QThread object again here - a
        # dangling Python reference read after deleteLater() actually runs
        # (e.g. during a settings dialog's nested event loop) raised
        # "QThread object already deleted".
        if self._watchdog is not None:
            self._watchdog.stop()
            self._watchdog = None
        self._refreshing = False
        self._thread = None
        self._worker = None

    def _on_refresh_watchdog_timeout(self) -> None:
        # The worker thread never finished within WATCHDOG_TIMEOUT_MS -
        # stop waiting on it instead of leaving _refreshing stuck True
        # forever (which would silently no-op every future refresh_now()
        # call, timer-driven or manual, with no visible error at all).
        # Disconnect our own slots first so if the stuck call eventually
        # does complete, it can't clobber state for whatever refresh runs
        # next; deleteLater() stays connected so Qt still cleans it up.
        if self._worker is not None:
            try:
                self._worker.succeeded.disconnect(self._on_refresh_succeeded)
                self._worker.failed.disconnect(self._on_refresh_failed)
            except (RuntimeError, TypeError):
                pass
        if self._thread is not None:
            try:
                self._thread.finished.disconnect(self._on_thread_finished)
            except (RuntimeError, TypeError):
                pass
        self._watchdog = None
        self._thread = None
        self._worker = None
        self._refreshing = False
        self._on_refresh_failed(
            "새로고침이 응답 없이 멈춰서 건너뜁니다 (네트워크/절전 문제로 추정). 다음 주기 또는 수동 새로고침에서 다시 시도합니다."
        )

    def _on_refresh_succeeded(self, result: RefreshResult) -> None:
        self._last_result = result
        snap = result.snapshot
        self.tray.setIcon(make_icon(snap.usage_pct, snap.color))
        tooltip = (
            f"Copilot 사용량: {snap.used:,.0f} / {snap.quota:,.0f} ({snap.usage_pct:.1f}%)\n"
            f"상태: {snap.label} | 영업일 {snap.elapsed_bdays}/{snap.total_bdays}\n"
            f"업데이트: {result.last_updated.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        if result.warnings:
            tooltip += "\n⚠ " + "; ".join(result.warnings)
        self.tray.setToolTip(tooltip)
        self.status_action.setText(f"사용량 {snap.usage_pct:.1f}% ({snap.label})")

        if self.detail_window is not None and self.detail_window.isVisible():
            self.detail_window.update_result(result)

    def _on_refresh_failed(self, message: str) -> None:
        self.tray.setIcon(make_error_icon())
        self.tray.setToolTip(f"Copilot 사용량 모니터 - 오류: {message}")
        self.status_action.setText("상태: 오류 (설정/토큰 확인)")
        if self.detail_window is not None and self.detail_window.isVisible():
            self.detail_window.show_error(message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Qt's default font fallback for Hangul glyphs resolves to the legacy
    # "Gulim" bitmap font on Windows instead of the modern Malgun Gothic;
    # pin it explicitly so dialogs/menus render correctly. Windows-only:
    # these font names don't exist on macOS/Linux and just log "not found"
    # there, where the platform default already renders Hangul correctly.
    if sys.platform == "win32":
        ui_font = QFont()
        ui_font.setFamilies(["Malgun Gothic", "Segoe UI"])
        app.setFont(ui_font)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "오류", "시스템 트레이를 사용할 수 없는 환경입니다.")
        return 1

    tray_app = TrayApp(app)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
