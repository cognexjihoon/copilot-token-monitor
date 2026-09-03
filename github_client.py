"""Client for GitHub's Copilot AI Credit / Premium Request billing usage API.

Endpoints (GitHub REST, 2026):
  GET /users/{username}/settings/billing/{kind}/usage
  GET /organizations/{org}/settings/billing/{kind}/usage
where {kind} is "ai_credit" or "premium_request". Both accept
year/month/day query params; omitting `day` returns the whole month's
total. There is no per-item date field, so a daily trend is built by
calling once per day (see usage_cache.py for caching that).
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

API_BASE = "https://api.github.com"
API_VERSION = "2026-03-10"


class GitHubApiError(RuntimeError):
    pass


@dataclass
class UsageResult:
    net_quantity: float
    raw: dict


class CopilotUsageClient:
    def __init__(self, token: str, username: str, org: str, auth_mode: str, endpoint_kind: str):
        self.token = token
        self.username = username
        self.org = org
        self.auth_mode = auth_mode
        self.endpoint_kind = endpoint_kind
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            }
        )

    def _url(self) -> str:
        if self.auth_mode == "org":
            return f"{API_BASE}/organizations/{self.org}/settings/billing/{self.endpoint_kind}/usage"
        return f"{API_BASE}/users/{self.username}/settings/billing/{self.endpoint_kind}/usage"

    def _get(self, year: int, month: int, day: int | None = None) -> UsageResult:
        params = {"year": year, "month": month}
        if day is not None:
            params["day"] = day
        if self.auth_mode == "org":
            params["user"] = self.username
        try:
            resp = self._session.get(self._url(), params=params, timeout=20)
        except requests.RequestException as exc:
            raise GitHubApiError(f"네트워크 오류: {exc}") from exc

        if resp.status_code == 401:
            raise GitHubApiError("인증 실패: 토큰이 유효하지 않습니다.")
        if resp.status_code == 403:
            raise GitHubApiError("권한 없음: 토큰에 billing 조회 권한이 없거나 조직 관리자 권한이 필요합니다.")
        if resp.status_code == 404:
            raise GitHubApiError("찾을 수 없음: 사용자/조직명 또는 엔드포인트 종류를 확인하세요.")
        if not resp.ok:
            raise GitHubApiError(f"API 오류 ({resp.status_code}): {resp.text[:300]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise GitHubApiError(f"응답 파싱 실패: {exc}") from exc

        total = sum(float(item.get("netQuantity", 0) or 0) for item in data.get("usageItems", []))
        return UsageResult(net_quantity=total, raw=data)

    def get_month_total(self, year: int, month: int) -> UsageResult:
        return self._get(year, month)

    def get_day_total(self, year: int, month: int, day: int) -> UsageResult:
        return self._get(year, month, day)

    def test_connection(self, year: int, month: int) -> tuple[bool, str]:
        try:
            result = self.get_month_total(year, month)
        except GitHubApiError as exc:
            return False, str(exc)
        return True, f"연결 성공. 이번 달 누적 사용량: {result.net_quantity:g}"
