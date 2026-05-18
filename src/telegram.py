"""Telegram Bot API delivery."""

from __future__ import annotations

import logging
import os

import requests


LOGGER = logging.getLogger(__name__)
TELEGRAM_API_BASE = "https://api.telegram.org"
REQUEST_TIMEOUT_SECONDS = 20


def telegram_configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def send_telegram_message(text: str) -> bool:
    """Send a message to Telegram. Returns True only when Telegram accepts it."""
    if not text.strip():
        LOGGER.info("Skipping empty Telegram message.")
        return False

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        LOGGER.warning("Telegram credentials are not configured; message was not sent.")
        return False

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.error("Telegram send failed: %s", exc)
        return False

    body = response.json()
    if not body.get("ok"):
        LOGGER.error("Telegram rejected message: %s", body)
        return False
    return True


def format_opportunity_message(opportunity: dict) -> str:
    matched = ", ".join(opportunity.get("matched_keywords", [])) or "None"
    deadline = opportunity.get("deadline") or "Not listed"

    if opportunity.get("type") == "funding":
        return "\n".join(
            [
                "🚀 New Funding Opportunity for Engocha",
                "",
                f"Title: {opportunity.get('title', 'Untitled')}",
                f"Source: {opportunity.get('source', 'Unknown')}",
                f"Deadline: {deadline}",
                f"Fit Score: {opportunity.get('score', 0)}",
                f"Matched Keywords: {matched}",
                f"Why it fits Engocha: {opportunity.get('why_it_fits', '')}",
                f"Link: {opportunity.get('link', '')}",
            ]
        )

    return "\n".join(
        [
            "💼 New Job Opportunity",
            "",
            f"Title: {opportunity.get('title', 'Untitled')}",
            f"Organization/Source: {opportunity.get('organization') or opportunity.get('source', 'Unknown')}",
            f"Location: {opportunity.get('location') or 'Not listed'}",
            f"Fit Score: {opportunity.get('score', 0)}",
            f"Matched Keywords: {matched}",
            f"Why it fits me: {opportunity.get('why_it_fits', '')}",
            f"Link: {opportunity.get('link', '')}",
        ]
    )


def format_run_summary(summary: dict) -> str:
    return "\n".join(
        [
            "✅ Opportunity Alert Bot Ran",
            "",
            f"Collected: {summary.get('collected', 0)}",
            f"Already Seen: {summary.get('already_seen', 0)}",
            f"Below Score: {summary.get('below_score', 0)}",
            f"Not Relevant: {summary.get('not_relevant', 0)}",
            f"New Matches: {summary.get('new_matches', 0)}",
            f"Alerts Sent: {summary.get('sent', 0)}",
        ]
    )
