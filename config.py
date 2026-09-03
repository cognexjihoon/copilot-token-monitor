"""Application configuration: load/save + Windows DPAPI encryption of the PAT."""
from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import win32crypt  # type: ignore

    _HAS_DPAPI = True
except ImportError:
    _HAS_DPAPI = False

APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "CopilotUsageMonitor"
CONFIG_PATH = APP_DIR / "config.json"
CACHE_PATH = APP_DIR / "usage_cache.json"


def _encrypt(token: str) -> str:
    if not token:
        return ""
    if _HAS_DPAPI:
        blob = win32crypt.CryptProtectData(token.encode("utf-8"), "CopilotUsageMonitor", None, None, None, 0)
        return "dpapi:" + base64.b64encode(blob).decode("ascii")
    return "plain:" + token


def _decrypt(stored: str) -> str:
    if not stored:
        return ""
    kind, _, payload = stored.partition(":")
    if kind == "dpapi" and _HAS_DPAPI:
        raw = base64.b64decode(payload)
        _, decrypted = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
        return decrypted.decode("utf-8")
    if kind == "plain":
        return payload
    return ""


@dataclass
class AppConfig:
    auth_mode: str = "user"  # "user" or "org"
    endpoint_kind: str = "ai_credit"  # "ai_credit" or "premium_request"
    username: str = ""
    org: str = ""
    enterprise: str = ""  # used when quota_source == "budget_api"
    monthly_quota: float = 20000.0  # used when quota_source == "manual"
    quota_source: str = "manual"  # "manual", "budget_api", or "scrape"
    poll_interval_min: int = 30
    _token_plain: str = field(default="", repr=False, compare=False)  # only used in-memory
    _cookie_plain: str = field(default="", repr=False, compare=False)  # only used in-memory

    def token(self) -> str:
        return self._token_plain

    def set_token(self, value: str) -> None:
        self._token_plain = value or ""

    def cookie(self) -> str:
        return self._cookie_plain

    def set_cookie(self, value: str) -> None:
        self._cookie_plain = value or ""

    @classmethod
    def load(cls) -> "AppConfig":
        if not CONFIG_PATH.exists():
            return cls()
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        cfg = cls(
            auth_mode=data.get("auth_mode", "user"),
            endpoint_kind=data.get("endpoint_kind", "ai_credit"),
            username=data.get("username", ""),
            org=data.get("org", ""),
            enterprise=data.get("enterprise", ""),
            monthly_quota=float(data.get("monthly_quota", 20000.0)),
            quota_source=data.get("quota_source", "manual"),
            poll_interval_min=int(data.get("poll_interval_min", 30)),
        )
        cfg.set_token(_decrypt(data.get("token_enc", "")))
        cfg.set_cookie(_decrypt(data.get("cookie_enc", "")))
        return cfg

    def save(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("_token_plain", None)
        data.pop("_cookie_plain", None)
        data["token_enc"] = _encrypt(self._token_plain)
        data["cookie_enc"] = _encrypt(self._cookie_plain)
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_valid(self) -> bool:
        if not self.token() or not self.username:
            return False
        if self.auth_mode == "org" and not self.org:
            return False
        return True
