from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config import AppConfig
from github_client import CopilotUsageClient, GitHubApiError
from scrape_client import ScrapeError, fetch_quota

AUTH_MODES = [("개인 계정 (user)", "user"), ("조직 (organization)", "org")]
ENDPOINT_KINDS = [("AI Credit (2026~ 신규 과금)", "ai_credit"), ("Premium Request (레거시)", "premium_request")]
QUOTA_SOURCES = [
    ("수동 입력", "manual"),
    ("Budget API (PAT, 관리자 권한 필요, 쿠키 불필요)", "budget_api"),
    ("GitHub 페이지에서 자동 감지 (쿠키 필요)", "scrape"),
]


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("설정 - Copilot 사용량 모니터")
        self.setMinimumWidth(440)
        self.config = config

        self.auth_mode_box = QComboBox()
        for label, _ in AUTH_MODES:
            self.auth_mode_box.addItem(label)
        self.org_edit = QLineEdit(config.org)
        self.org_edit.setPlaceholderText("조직 로그인명 (auth_mode=organization일 때만 사용)")

        self.endpoint_kind_box = QComboBox()
        for label, _ in ENDPOINT_KINDS:
            self.endpoint_kind_box.addItem(label)

        self.username_edit = QLineEdit(config.username)
        self.username_edit.setPlaceholderText("GitHub 사용자명 (예: octocat)")

        self.token_edit = QLineEdit(config.token())
        self.token_edit.setEchoMode(QLineEdit.Password)
        self.token_edit.setPlaceholderText("Personal Access Token (billing 조회 권한 필요)")

        self.quota_source_box = QComboBox()
        for label, _ in QUOTA_SOURCES:
            self.quota_source_box.addItem(label)

        self.quota_spin = QDoubleSpinBox()
        self.quota_spin.setRange(0, 10_000_000)
        self.quota_spin.setDecimals(0)
        self.quota_spin.setSuffix(" credits")
        self.quota_spin.setValue(config.monthly_quota)

        self.cookie_edit = QLineEdit(config.cookie())
        self.cookie_edit.setEchoMode(QLineEdit.Password)
        self.cookie_edit.setPlaceholderText("브라우저 DevTools > Network 에서 복사한 Cookie 헤더 값 전체")

        self.enterprise_edit = QLineEdit(config.enterprise)
        self.enterprise_edit.setPlaceholderText("엔터프라이즈 slug (Budget API 사용 시 필요)")

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 240)
        self.interval_spin.setSuffix(" 분")
        self.interval_spin.setValue(config.poll_interval_min)

        self._set_index(self.auth_mode_box, AUTH_MODES, config.auth_mode)
        self._set_index(self.endpoint_kind_box, ENDPOINT_KINDS, config.endpoint_kind)
        self._set_index(self.quota_source_box, QUOTA_SOURCES, config.quota_source)

        cookie_help = QLabel(
            "쿠키 얻는 법: 브라우저에서 github.com 로그인 → 개발자도구(F12) → Network 탭 → "
            "아무 github.com 요청 클릭 → Request Headers의 'cookie' 값 전체 복사.\n"
            "※ 세션 쿠키이므로 주기적으로 만료됩니다. 실패 시 새로 복사해 넣으세요."
        )
        cookie_help.setWordWrap(True)
        cookie_help.setStyleSheet("color: gray; font-size: 11px;")

        budget_help = QLabel(
            "Budget API 사용 조건: 토큰 소유자가 해당 엔터프라이즈의 관리자/billing manager여야 하고, "
            "관리자가 이 사용자에게 개별 AI credit budget을 설정해 두었어야 합니다. "
            "필요 스코프 예: manage_billing:enterprise, read:enterprise (classic PAT)."
        )
        budget_help.setWordWrap(True)
        budget_help.setStyleSheet("color: gray; font-size: 11px;")

        form = QFormLayout()
        form.addRow("계정 종류", self.auth_mode_box)
        form.addRow("조직명", self.org_edit)
        form.addRow("사용량 종류", self.endpoint_kind_box)
        form.addRow("GitHub 사용자명", self.username_edit)
        form.addRow("Personal Access Token", self.token_edit)
        form.addRow("월 한도(쿼터) 소스", self.quota_source_box)
        form.addRow("월 한도(수동/폴백)", self.quota_spin)
        form.addRow("엔터프라이즈 slug", self.enterprise_edit)
        form.addRow("", budget_help)
        form.addRow("세션 쿠키", self.cookie_edit)
        form.addRow("", cookie_help)
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

        self.auth_mode_box.currentIndexChanged.connect(self._sync_enabled)
        self.quota_source_box.currentIndexChanged.connect(self._sync_enabled)
        self._sync_enabled()

    @staticmethod
    def _set_index(box: QComboBox, options: list[tuple[str, str]], value: str) -> None:
        for i, (_, key) in enumerate(options):
            if key == value:
                box.setCurrentIndex(i)
                return

    def _sync_enabled(self) -> None:
        is_org = AUTH_MODES[self.auth_mode_box.currentIndex()][1] == "org"
        self.org_edit.setEnabled(is_org)
        quota_source = QUOTA_SOURCES[self.quota_source_box.currentIndex()][1]
        self.cookie_edit.setEnabled(quota_source == "scrape")
        self.enterprise_edit.setEnabled(quota_source == "budget_api")

    def _apply_to(self, cfg: AppConfig) -> None:
        cfg.auth_mode = AUTH_MODES[self.auth_mode_box.currentIndex()][1]
        cfg.endpoint_kind = ENDPOINT_KINDS[self.endpoint_kind_box.currentIndex()][1]
        cfg.username = self.username_edit.text().strip()
        cfg.org = self.org_edit.text().strip()
        cfg.set_token(self.token_edit.text().strip())
        cfg.quota_source = QUOTA_SOURCES[self.quota_source_box.currentIndex()][1]
        cfg.monthly_quota = self.quota_spin.value()
        cfg.enterprise = self.enterprise_edit.text().strip()
        cfg.set_cookie(self.cookie_edit.text().strip())
        cfg.poll_interval_min = self.interval_spin.value()

    def _on_test(self) -> None:
        temp = AppConfig()
        self._apply_to(temp)
        if not temp.is_valid():
            self.test_label.setText("❌ 사용자명/토큰(및 조직명)을 먼저 입력하세요.")
            return

        client = CopilotUsageClient(
            token=temp.token(),
            username=temp.username,
            org=temp.org,
            auth_mode=temp.auth_mode,
            endpoint_kind=temp.endpoint_kind,
        )
        today = date.today()
        ok, message = client.test_connection(today.year, today.month)

        if temp.quota_source == "budget_api" and temp.enterprise:
            try:
                amount = client.get_budget_amount(temp.enterprise)
                message += f"\nBudget API 조회 성공: {amount:g} credits"
            except GitHubApiError as exc:
                message += f"\nBudget API 조회 실패: {exc}"
        elif temp.quota_source == "scrape" and temp.cookie():
            try:
                scraped = fetch_quota(temp.cookie())
                message += f"\n쿼터 자동 감지 성공: {scraped.used:g} / {scraped.quota:g}"
            except ScrapeError as exc:
                message += f"\n쿼터 자동 감지 실패: {exc}"

        self.test_label.setText(("✅ " if ok else "❌ ") + message)

    def _on_accept(self) -> None:
        self._apply_to(self.config)
        if not self.config.is_valid():
            QMessageBox.warning(self, "설정 미완료", "사용자명/토큰(및 조직명일 경우 조직명)을 입력해야 합니다.")
            return
        try:
            self.config.save()
        except (OSError, GitHubApiError) as exc:
            QMessageBox.critical(self, "저장 실패", str(exc))
            return
        self.accept()
