from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import AppConfig
from login_window import GitHubLoginDialog
from scrape_client import ScrapeError, fetch_quota


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("설정 - Copilot 사용량 모니터")
        self.setMinimumWidth(440)
        self.config = config
        self._cookie = config.cookie()

        self.login_status_label = QLabel(self._login_status_text())

        login_btn = QPushButton("GitHub 로그인")
        login_btn.clicked.connect(self._on_login_clicked)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 240)
        self.interval_spin.setSuffix(" 분")
        self.interval_spin.setValue(config.poll_interval_min)

        form = QFormLayout()
        form.addRow("GitHub 계정", login_btn)
        form.addRow("", self.login_status_label)
        form.addRow("확인 주기", self.interval_spin)

        self.test_label = QLabel("")
        self.test_label.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        test_btn = buttons.addButton("연결 테스트", QDialogButtonBox.ActionRole)
        test_btn.clicked.connect(self._on_test)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.test_label)
        layout.addWidget(buttons)

    def _login_status_text(self) -> str:
        return "✅ 로그인됨" if self._cookie else "❌ 로그인이 필요합니다"

    def _on_login_clicked(self) -> None:
        dialog = GitHubLoginDialog(self)
        dialog.cookie_captured.connect(self._on_cookie_captured)
        dialog.exec()

    def _on_cookie_captured(self, cookie_header: str) -> None:
        self._cookie = cookie_header
        self.login_status_label.setText(self._login_status_text())
        self.test_label.setText("✅ 로그인 완료. '연결 테스트'로 확인해보세요.")

    def _apply_to(self, cfg: AppConfig) -> None:
        cfg.set_cookie(self._cookie)
        cfg.poll_interval_min = self.interval_spin.value()

    def _on_test(self) -> None:
        if not self._cookie:
            self.test_label.setText("❌ 먼저 GitHub 로그인을 진행하세요.")
            return
        try:
            scraped = fetch_quota(self._cookie)
        except ScrapeError as exc:
            self.test_label.setText(f"❌ {exc}")
            return
        self.test_label.setText(f"✅ 연결 성공. 사용량: {scraped.used:g} / {scraped.quota:g}")

    def _on_accept(self) -> None:
        self._apply_to(self.config)
        if not self.config.is_valid():
            self.test_label.setText("❌ GitHub 로그인을 먼저 진행해야 합니다.")
            return
        try:
            self.config.save()
        except OSError as exc:
            self.test_label.setText(f"❌ 저장 실패: {exc}")
            return
        self.accept()
