"""Application configuration: load/save + Windows DPAPI encryption of the
session cookie."""
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


def _encrypt(value: str) -> str:
    if not value:
        return ""
    if _HAS_DPAPI:
        blob = win32crypt.CryptProtectData(value.encode("utf-8"), "CopilotUsageMonitor", None, None, None, 0)
        return "dpapi:" + base64.b64encode(blob).decode("ascii")
    return "plain:" + value


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
    poll_interval_min: int = 30
    _cookie_plain: str = field(default="", repr=False, compare=False)  # only used in-memory

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
            poll_interval_min=int(data.get("poll_interval_min", 30)),
        )
        cfg.set_cookie(_decrypt(data.get("cookie_enc", "")))
        return cfg

    def save(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("_cookie_plain", None)
        data["cookie_enc"] = _encrypt(self._cookie_plain)
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_valid(self) -> bool:
        return bool(self.cookie())
