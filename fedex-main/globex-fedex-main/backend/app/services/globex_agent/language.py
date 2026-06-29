"""Résolution langue admin Globex Agent — message utilisateur prioritaire sur UI i18n."""

from __future__ import annotations

from app.services.ai_assistant.language_service import detect_message_language
from app.services.llm.providers import normalize_lang_code

_ADMIN_LANGS = frozenset({"fr", "en", "ar"})


def resolve_admin_chat_language(message: str, ui_language: str = "fr") -> str:
    """
    Langue de réponse admin : détectée depuis le message, repli sur ui_language.
    Sidebar (UI EN) + message FR → fr. Message EN → en.
    """
    detected = detect_message_language(message or "")
    hint = normalize_lang_code(ui_language)
    if hint not in _ADMIN_LANGS:
        hint = "fr"
    if detected in _ADMIN_LANGS:
        return detected
    return hint
