import pytest
import requests

import teams_notifier
from teams_notifier import send_teams_message


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise requests.exceptions.HTTPError(f"{self.status_code} error")


def test_send_teams_message_posts_adaptive_card(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(200)

    monkeypatch.setattr(teams_notifier.requests, "post", fake_post)

    send_teams_message("https://example.com/webhook", "제목", "본문")

    assert captured["url"] == "https://example.com/webhook"
    card = captured["json"]["attachments"][0]["content"]
    texts = [block["text"] for block in card["body"]]
    assert texts == ["제목", "본문"]


def test_send_teams_message_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(teams_notifier.requests, "post", lambda *a, **k: FakeResponse(500))

    with pytest.raises(requests.exceptions.HTTPError):
        send_teams_message("https://example.com/webhook", "제목", "본문")


def test_send_teams_message_propagates_network_error(monkeypatch):
    def _raise(*a, **k):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(teams_notifier.requests, "post", _raise)

    with pytest.raises(requests.exceptions.ConnectionError):
        send_teams_message("https://example.com/webhook", "제목", "본문")
