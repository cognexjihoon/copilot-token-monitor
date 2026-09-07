"""Sends a message to Microsoft Teams via a Workflows incoming webhook
(the classic Office 365 Connector incoming webhook was retired in 2026;
this is its replacement). Works for either a *channel* webhook or a
*chat* webhook (e.g. a chat with yourself, for a personal-message-only
alert) - both accept the same Adaptive Card payload below, so this
module doesn't need to know which kind of webhook URL it was given.
See SettingsDialog's Teams webhook help popup (ui_settings.py) for the
exact click-path to create one. No Azure app registration or auth needed
here, the URL itself is the credential.
"""
from __future__ import annotations

import requests

TIMEOUT_SEC = 10


def send_teams_message(webhook_url: str, title: str, text: str) -> None:
    """Raises requests.RequestException on failure. Callers should treat a
    failed notification as non-fatal - it must never break the usage poll
    loop, so this deliberately doesn't wrap failures in a custom error
    type the way scrape_client.ScrapeError does."""
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True},
                        {"type": "TextBlock", "text": text, "wrap": True},
                    ],
                },
            }
        ],
    }
    resp = requests.post(webhook_url, json=payload, timeout=TIMEOUT_SEC)
    resp.raise_for_status()
