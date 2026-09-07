from __future__ import annotations

import requests
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import AppConfig
from login_window import GitHubLoginDialog
from scrape_client import ScrapeError, fetch_quota
from teams_notifier import send_teams_message


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

        self.teams_webhook_edit = QLineEdit(config.teams_webhook_url)
        self.teams_webhook_edit.setPlaceholderText("https://<tenant>.webhook.office.com/... (선택)")

        teams_webhook_help_btn = QPushButton("?")
        teams_webhook_help_btn.setFixedWidth(28)
        teams_webhook_help_btn.setToolTip("Teams Webhook URL 만드는 방법")
        teams_webhook_help_btn.clicked.connect(self._on_teams_webhook_help)

        teams_webhook_row = QHBoxLayout()
        teams_webhook_row.addWidget(self.teams_webhook_edit)
        teams_webhook_row.addWidget(teams_webhook_help_btn)

        self.teams_threshold_spin = QDoubleSpinBox()
        self.teams_threshold_spin.setRange(1.0, 100.0)
        self.teams_threshold_spin.setSuffix(" %")
        self.teams_threshold_spin.setDecimals(0)
        self.teams_threshold_spin.setValue(config.teams_threshold_pct)

        teams_test_btn = QPushButton("Teams 알림 테스트")
        teams_test_btn.clicked.connect(self._on_teams_test)
        self.teams_test_label = QLabel("")
        self.teams_test_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("GitHub 계정", login_btn)
        form.addRow("", self.login_status_label)
        form.addRow("확인 주기", self.interval_spin)
        form.addRow("Teams Webhook URL", teams_webhook_row)
        form.addRow("Teams 알림 임계치", self.teams_threshold_spin)
        form.addRow("", teams_test_btn)
        form.addRow("", self.teams_test_label)

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
        cfg.teams_webhook_url = self.teams_webhook_edit.text().strip()
        cfg.teams_threshold_pct = self.teams_threshold_spin.value()

    def _on_teams_webhook_help(self) -> None:
        QMessageBox.information(
            self,
            "Teams Webhook URL 만드는 방법",
            "<b>채팅으로 알림 받기</b><br><br>"
            "1. Teams 왼쪽 앱바에서 <b>Workflows</b> 아이콘을 클릭하세요.<br>"
            "&nbsp;&nbsp;&nbsp;(안 보이면 앱바 아래쪽 \"더보기 앱(···)\"에서 검색)<br>"
            "2. 템플릿 검색창에 <b>\"Send webhook alerts to a chat\"</b>를 검색해서 선택하세요.<br>"
            "3. 채팅에서 본인의 이름을 선택하고 저장 버튼을 눌러주세요.<br>"
            "4. 만들기를 완료하면 <b>\"웹후크 링크 복사\"</b> 버튼을 클릭합니다.<br>"
            "5. 이 URL을 왼쪽 \"Teams Webhook URL\"란에 붙여넣고 "
            "\"Teams 알림 테스트\" 버튼으로 확인하세요.",
        )

    def _on_teams_test(self) -> None:
        webhook_url = self.teams_webhook_edit.text().strip()
        if not webhook_url:
            self.teams_test_label.setText("❌ 먼저 Teams Webhook URL을 입력하세요.")
            return
        try:
            send_teams_message(
                webhook_url,
                "✅ Copilot 사용량 모니터",
                "Teams 알림 연결 테스트입니다. 이 메시지가 보이면 정상 연결된 것입니다.",
            )
        except requests.RequestException as exc:
            self.teams_test_label.setText(f"❌ 전송 실패: {exc}")
            return
        self.teams_test_label.setText("✅ 전송 성공. Teams에서 확인하세요.")

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
