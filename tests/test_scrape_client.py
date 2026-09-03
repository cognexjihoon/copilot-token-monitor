import requests

import scrape_client
from scrape_client import ScrapeError, fetch_quota


class FakeResponse:
    def __init__(self, text="", status_code=200, url=scrape_client.BILLING_URL, ok=None):
        self.text = text
        self.status_code = status_code
        self.url = url
        self.ok = (200 <= status_code < 400) if ok is None else ok


def test_fetch_quota_requires_cookie():
    try:
        fetch_quota("")
        assert False, "expected ScrapeError"
    except ScrapeError as exc:
        assert "쿠키" in str(exc)


def test_fetch_quota_parses_comma_formatted_numbers(monkeypatch):
    html = "<div>Usage this period: 2,595 / 20,000 AI credits used</div>"
    monkeypatch.setattr(scrape_client.requests, "get", lambda *a, **k: FakeResponse(text=html))

    result = fetch_quota("user_session=abc")

    assert result.used == 2595.0
    assert result.quota == 20000.0


def test_fetch_quota_parses_no_comma_numbers_case_insensitive(monkeypatch):
    html = "<span>250/1000 ai Credit</span>"
    monkeypatch.setattr(scrape_client.requests, "get", lambda *a, **k: FakeResponse(text=html))

    result = fetch_quota("user_session=abc")

    assert result.used == 250.0
    assert result.quota == 1000.0


def test_fetch_quota_ignores_other_meters_on_the_same_page(monkeypatch):
    html = (
        "<div>1,000 / 2,000 premium request</div>"
        "<div>2,595 / 20,000 AI credits used</div>"
    )
    monkeypatch.setattr(scrape_client.requests, "get", lambda *a, **k: FakeResponse(text=html))

    result = fetch_quota("user_session=abc")

    # the pattern is anchored to the literal "AI credit" text, so a premium
    # request meter earlier on the page must not be picked up instead
    assert (result.used, result.quota) == (2595.0, 20000.0)


def test_fetch_quota_picks_first_meter_when_two_ai_credit_meters_present(monkeypatch):
    # documents current (fragile) behavior: if the page ever renders two "AI
    # credit" meters, the regex has no way to disambiguate and just takes
    # whichever occurs first in the HTML
    html = (
        "<div>1,000 / 2,000 AI credit</div>"
        "<div>2,595 / 20,000 AI credits used</div>"
    )
    monkeypatch.setattr(scrape_client.requests, "get", lambda *a, **k: FakeResponse(text=html))

    result = fetch_quota("user_session=abc")

    assert (result.used, result.quota) == (1000.0, 2000.0)


def test_fetch_quota_no_match_raises_scrape_error(monkeypatch):
    monkeypatch.setattr(
        scrape_client.requests, "get", lambda *a, **k: FakeResponse(text="<div>nothing here</div>")
    )

    try:
        fetch_quota("user_session=abc")
        assert False, "expected ScrapeError"
    except ScrapeError as exc:
        assert "찾지 못했습니다" in str(exc)


def test_fetch_quota_expired_session_via_status_code(monkeypatch):
    monkeypatch.setattr(
        scrape_client.requests, "get", lambda *a, **k: FakeResponse(status_code=401, ok=False)
    )

    try:
        fetch_quota("user_session=expired")
        assert False, "expected ScrapeError"
    except ScrapeError as exc:
        assert "만료" in str(exc)


def test_fetch_quota_expired_session_via_login_redirect(monkeypatch):
    monkeypatch.setattr(
        scrape_client.requests,
        "get",
        lambda *a, **k: FakeResponse(status_code=200, url="https://github.com/login"),
    )

    try:
        fetch_quota("user_session=expired")
        assert False, "expected ScrapeError"
    except ScrapeError as exc:
        assert "만료" in str(exc)


def test_fetch_quota_non_ok_status_raises(monkeypatch):
    monkeypatch.setattr(
        scrape_client.requests, "get", lambda *a, **k: FakeResponse(status_code=500, ok=False)
    )

    try:
        fetch_quota("user_session=abc")
        assert False, "expected ScrapeError"
    except ScrapeError as exc:
        assert "500" in str(exc)


def test_fetch_quota_network_error_wrapped(monkeypatch):
    def _raise(*a, **k):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(scrape_client.requests, "get", _raise)

    try:
        fetch_quota("user_session=abc")
        assert False, "expected ScrapeError"
    except ScrapeError as exc:
        assert "네트워크" in str(exc)


def test_fetch_quota_sends_cookie_header(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, timeout=None, allow_redirects=None):
        captured["url"] = url
        captured["headers"] = headers
        return FakeResponse(text="100 / 200 AI credit")

    monkeypatch.setattr(scrape_client.requests, "get", fake_get)

    fetch_quota("user_session=abc; _gh_sess=def")

    assert captured["url"] == scrape_client.BILLING_URL
    assert captured["headers"]["Cookie"] == "user_session=abc; _gh_sess=def"
