"""Espace de travail Security IDS admin — gate Jarvis."""

from __future__ import annotations

from app.services.admin_client.security.security_followup import is_security_followup_message
from app.services.admin_client.security.security_patterns import (
    is_logs_anomaly_scope,
    score_security_utterance,
)


def is_security_workspace(message: str, *, history_text: str = "") -> bool:
    text = (message or "").strip()
    if not text or is_logs_anomaly_scope(text):
        return False
    if is_security_followup_message(text, history_text=history_text):
        return True
    return score_security_utterance(text) >= 2.0


def score_security_soft(message: str) -> float:
    return score_security_utterance(message)
