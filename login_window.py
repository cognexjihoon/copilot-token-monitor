"""Embedded-browser GitHub login so users don't have to dig through DevTools
to copy a session cookie by hand.

Opens a real Chromium view (QWebEngineView) pointed at github.com/login.
The user logs in exactly like in a normal browser - including any
organization SAML SSO redirect and 2FA prompt, which we never touch or
automate. Once the browser lands back on a logged-in github.com page, we
read the accumulated cookies for the github.com domain and hand back the
same "Cookie:" header string a user would otherwise copy from DevTools.

The profile is created with NoPersistentCookies so nothing is written to
disk by Qt itself; the captured cookie string is the only thing the caller
persists (DPAPI-encrypted, see config.py).
"""
from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

LOGIN_URL = "https://github.com/login"
# Cookies whose presence indicates an authenticated github.com session.
_SESSION_MARKERS = {"user_session", "logged_in", "dotcom_user"}


class GitHubLoginDialog(QDialog):
    """Modal dialog that returns a raw `Cookie:` header string via
    `cookie_captured` once the embedded browser detects a logged-in session."""

    cookie_captured = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("GitHub 로그인")
        self.resize(480, 720)
        self._cookies: dict[str, str] = {}
        self._done = False

        self._profile = QWebEngineProfile("copilot-usage-monitor-login", self)
        self._profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self._profile.cookieStore().cookieAdded.connect(self._on_cookie_added)

        self._page = QWebEnginePage(self._profile, self)
        self.view = QWebEngineView(self)
        self.view.setPage(self._page)
        self.view.urlChanged.connect(self._on_url_changed)

        info = QLabel(
            "평소처럼 GitHub(회사 SSO 포함)에 로그인하세요. 로그인이 완료되면 이 창이 자동으로 닫힙니다."
        )
        info.setWordWrap(True)

        manual_btn = QPushButton("로그인했는데 자동으로 안 닫히면 여기를 누르세요")
        manual_btn.clicked.connect(self._finish)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(self.view, stretch=1)
        layout.addWidget(manual_btn)

        self.view.load(QUrl(LOGIN_URL))

    def _on_cookie_added(self, cookie: QNetworkCookie) -> None:
        domain = cookie.domain().lstrip(".")
        if not domain.endswith("github.com"):
            return
        name = bytes(cookie.name()).decode("utf-8", "ignore")
        value = bytes(cookie.value()).decode("utf-8", "ignore")
        self._cookies[name] = value

    def _on_url_changed(self, qurl: QUrl) -> None:
        host = qurl.host()
        path = qurl.path()
        if not host.endswith("github.com"):
            return
        if path.startswith("/login") or path.startswith("/session") or path.startswith("/sessions"):
            return
        if _SESSION_MARKERS & self._cookies.keys():
            self._finish()

    def _finish(self) -> None:
        if self._done or not self._cookies:
            return
        self._done = True
        cookie_header = "; ".join(f"{name}={value}" for name, value in self._cookies.items())
        self.cookie_captured.emit(cookie_header)
        self.accept()
