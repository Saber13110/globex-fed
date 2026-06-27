"""Ollama résumé notifications + repli factuel."""

from __future__ import annotations

import logging

from app.schemas.user_notifications import UserNotificationRead
from app.services.client_phase5.notification_factual_summary import (
    build_factual_notification_summary,
    build_notifications_transcript,
)
from app.services.client_phase5.router_prompt import (
    NOTIFICATION_SUMMARY_PROMPT_EN,
    NOTIFICATION_SUMMARY_PROMPT_FR,
)
from app.services.client_phase4.session_summary_validator import is_acceptable_summary
from app.services.llm.providers import LlmProviderError, call_ollama_session_summary
from app.services.llm.prompts import language_lock_instruction

logger = logging.getLogger(__name__)


def _strict_system_prompt(lang: str) -> str:
    base = NOTIFICATION_SUMMARY_PROMPT_EN if lang == "en" else NOTIFICATION_SUMMARY_PROMPT_FR
    return f"{base}\n{language_lock_instruction(lang)}"


def generate_notifications_summary(
    items: list[UserNotificationRead],
    *,
    lang: str,
    filter_label: str = "",
) -> str:
    transcript = build_notifications_transcript(items)
    if not transcript.strip():
        return build_factual_notification_summary(items, lang=lang, filter_label=filter_label)

    title = "Notifications client"
    try:
        raw = call_ollama_session_summary(
            transcript,
            session_title=title,
            ui_language=lang,
            system_prompt=_strict_system_prompt(lang),
        )
        candidate = (raw or "").strip()
        if candidate and is_acceptable_summary(candidate, transcript, session_title=title):
            return candidate
    except LlmProviderError:
        logger.warning("notification summary Ollama failed, factual fallback", exc_info=True)

    factual = build_factual_notification_summary(items, lang=lang, filter_label=filter_label)
    return factual if factual.strip() else transcript[:800]
