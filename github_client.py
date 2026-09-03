"""Client for GitHub's Copilot billing usage and budget APIs.

Usage endpoints (GitHub REST, 2026):
  GET /users/{username}/settings/billing/{kind}/usage
  GET /organizations/{org}/settings/billing/{kind}/usage
where {kind} is "ai_credit" or "premium_request". Both accept
year/month/day query params; omitting `day` returns the whole month's
total. There is no per-item date field, so a daily trend is built by
calling once per day (see usage_cache.py for caching that).

Budget endpoint (GA since 2026-06), used to read the monthly quota
ceiling itself - something the usage endpoints above never return:
  GET /enterprises/{enterprise}/settings/billing/budgets?user={username}
This requires the token's holder to be an enterprise admin or billing
manager; a token without that role gets a 403 here even though the
same token can read its own usage fine.
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

    def _request(self, url: str, params: dict) -> dict:
        try:
            resp = self._session.get(url, params=params, timeout=20)
        except requests.RequestException as exc:
            raise GitHubApiError(f"네트워크 오류: {exc}") from exc

        if resp.status_code == 401:
            raise GitHubApiError("인증 실패: 토큰이 유효하지 않습니다.")
        if resp.status_code == 403:
            raise GitHubApiError("권한 없음: 토큰에 필요한 billing 조회 권한(또는 관리자 권한)이 없습니다.")
        if resp.status_code == 404:
            raise GitHubApiError("찾을 수 없음: 사용자명/조직명/엔터프라이즈명 또는 엔드포인트를 확인하세요.")
        if not resp.ok:
            raise GitHubApiError(f"API 오류 ({resp.status_code}): {resp.text[:300]}")

        try:
            return resp.json()
        except ValueError as exc:
            raise GitHubApiError(f"응답 파싱 실패: {exc}") from exc

    def _get(self, year: int, month: int, day: int | None = None) -> UsageResult:
        params = {"year": year, "month": month}
        if day is not None:
            params["day"] = day
        if self.auth_mode == "org":
            params["user"] = self.username
        data = self._request(self._url(), params)
        total = sum(float(item.get("netQuantity", 0) or 0) for item in data.get("usageItems", []))
        return UsageResult(net_quantity=total, raw=data)

    def get_month_total(self, year: int, month: int) -> UsageResult:
        return self._get(year, month)

    def get_day_total(self, year: int, month: int, day: int) -> UsageResult:
        return self._get(year, month, day)

    def get_budget_amount(self, enterprise: str) -> float:
        """Reads the user's AI-credit budget ceiling via the enterprise Budget
        API (GA 2026-06). Requires the token holder to be an enterprise admin
        or billing manager - a 403 here means the token lacks that role even
        if usage calls above work fine."""
        url = f"{API_BASE}/enterprises/{enterprise}/settings/billing/budgets"
        data = self._request(url, {"user": self.username})
        budgets = data.get("budgets", [])
        for budget in budgets:
            sku = str(budget.get("budget_product_sku", "")).lower()
            scope = str(budget.get("budget_scope", "")).lower()
            if "credit" in sku and (scope == "user" or budget.get("user") == self.username):
                return float(budget.get("budget_amount", 0))
        raise GitHubApiError(
            f"'{self.username}' 사용자의 AI credit 예산(budget)을 찾지 못했습니다. "
            "관리자가 개별 budget을 설정하지 않았을 수 있습니다."
        )

    def test_connection(self, year: int, month: int) -> tuple[bool, str]:
        try:
            result = self.get_month_total(year, month)
        except GitHubApiError as exc:
            return False, str(exc)
        return True, f"연결 성공. 이번 달 누적 사용량: {result.net_quantity:g}"
