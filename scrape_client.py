"""Best-effort scraper for the monthly AI-credit quota shown on github.com.

GitHub's billing usage API returns *usage* but never the plan's included
*quota* (the "20,000" ceiling) - that number only exists on a rendered
page, in a string like "2,595 / 20,000 AI credits used". This module
fetches that page using a browser session cookie the user copies from
their own logged-in browser (no password/2FA automation) and
regex-extracts the two numbers.

Note: /settings/billing itself is a client-side rendered React page whose
usage numbers load asynchronously after an XHR - they're never present in
the initial HTML `requests` sees. /settings/copilot/features is still a
classic server-rendered page with the "X / Y AI credit" string baked
directly into the HTML, so that's the one this module actually fetches.

This is inherently fragile: GitHub can change the markup/wording at any
time, and the session cookie expires periodically. Callers should treat
a failure here as non-fatal and fall back to the last known / manually
entered quota.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

BILLING_URL = "https://github.com/settings/copilot/features"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Matches e.g. "2,595 / 20,000 AI credit" or "2595/20000 AI Credits"
_PATTERN = re.compile(r"([\d,]+)\s*/\s*([\d,]+)\s*AI\s*credit", re.IGNORECASE)


class ScrapeError(RuntimeError):
    pass


@dataclass
class ScrapedQuota:
    used: float
    quota: float


def fetch_quota(cookie_header: str) -> ScrapedQuota:
    """cookie_header: the raw value of the browser's `Cookie` request header
    for github.com (copy from DevTools > Network > any github.com request),
    e.g. "user_session=...; _gh_sess=...; ..."."""
    if not cookie_header:
        raise ScrapeError("세션 쿠키가 설정되지 않았습니다.")

    try:
        resp = requests.get(
            BILLING_URL,
            headers={"Cookie": cookie_header, "User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=20,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise ScrapeError(f"네트워크 오류: {exc}") from exc

    if resp.status_code in (401, 403) or "/login" in resp.url:
        raise ScrapeError("로그인 세션이 만료되었습니다. 브라우저에서 다시 로그인 후 쿠키를 갱신하세요.")
    if not resp.ok:
        raise ScrapeError(f"페이지 요청 실패 ({resp.status_code})")

    match = _PATTERN.search(resp.text)
    if not match:
        raise ScrapeError(
            "페이지에서 'X / Y AI credit' 형식을 찾지 못했습니다. "
            "GitHub이 페이지 구조를 변경했을 수 있습니다 - 수동 입력으로 전환하세요."
        )

    used = float(match.group(1).replace(",", ""))
    quota = float(match.group(2).replace(",", ""))
    return ScrapedQuota(used=used, quota=quota)
