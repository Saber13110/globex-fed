"""Espace de travail journaux d'activité admin — gate Jarvis."""

from __future__ import annotations

from app.services.admin_client.logs.logs_followup import is_logs_followup_message
from app.services.admin_client.logs.logs_patterns import (
    is_user_scoped_logs_message,
    score_logs_utterance,
)


def is_logs_workspace(message: str, *, history_text: str = "") -> bool:
    text = (message or "").strip()
    if not text or is_user_scoped_logs_message(text):
        return False
    if is_logs_followup_message(text, history_text=history_text):
        return True
    return score_logs_utterance(text) >= 2.0


def score_logs_soft(message: str) -> float:
    return score_logs_utterance(message)
