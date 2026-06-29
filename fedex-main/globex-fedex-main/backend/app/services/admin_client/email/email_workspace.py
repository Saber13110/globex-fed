"""Espace de travail e-mail admin → utilisateur."""

from __future__ import annotations

from app.services.admin_client.email.email_patterns import (
    is_send_user_email_message,
    score_email_utterance,
)


def is_email_workspace(message: str, *, history_text: str = "") -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return is_send_user_email_message(text)


def score_email_soft(message: str) -> float:
    return score_email_utterance(message)
