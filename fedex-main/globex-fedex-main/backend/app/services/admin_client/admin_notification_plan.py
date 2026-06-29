"""Normalisation des plans notifications admin — limites FR, liste par défaut."""

from __future__ import annotations

import re
from typing import Any

from app.services.client_phase5.notification_filters import (
    CHAT_LIST_MAX,
    extract_notification_limit,
    normalize_message_text,
)

_FR_NUMBER_WORDS: dict[str, int] = {
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
}

_WORD_ALT = "|".join(sorted(_FR_NUMBER_WORDS.keys(), key=len, reverse=True))

_FR_LIMIT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(rf"\b(?:dernier|derniers|derni[eè]res?|dernieres)\s+({_WORD_ALT})\b", re.I),
    re.compile(rf"\b({_WORD_ALT})\s+(?:derni[eè]res?|derniers?|notifications?|notifs?|alertes?)\b", re.I),
    re.compile(rf"\bjuste\s+les?\s+({_WORD_ALT})\b", re.I),
    re.compile(rf"\b(?:les?\s+)?({_WORD_ALT})\s+premiers?\b", re.I),
]

_LIST_VERBS_RE = re.compile(
    r"\b(montre|montrez|liste|lister|affiche|affichez|donne|donnez|voir)\b",
    re.I,
)
_SUMMARIZE_RE = re.compile(r"\b(resume|resumer|recap|recapitulatif|synthese|synthèse|résumé)\b", re.I)


def extract_admin_notification_limit(message: str) -> int | None:
    """Limite explicite : chiffres (Phase 5) puis mots français (deux, trois…)."""
    numeric = extract_notification_limit(message)
    if numeric is not None:
        return min(max(numeric, 1), CHAT_LIST_MAX)

    text = normalize_message_text(message)
    for pattern in _FR_LIMIT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        word = match.group(1).lower()
        value = _FR_NUMBER_WORDS.get(word)
        if value is not None:
            return min(max(value, 1), CHAT_LIST_MAX)
    return None


def _wants_explicit_summarize(message: str) -> bool:
    return bool(_SUMMARIZE_RE.search(normalize_message_text(message)))


def _wants_list(message: str) -> bool:
    return bool(_LIST_VERBS_RE.search(normalize_message_text(message)))


def reconcile_admin_notification_plan(message: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Force liste par défaut (sauf résumé explicite) et applique la limite admin."""
    if not plan:
        return plan

    task = plan.get("task_type")
    if task in {"notifications_mark_all_read"} or plan.get("needs_clarification"):
        return plan

    if task != "notifications_query":
        return plan

    answers = dict(plan.get("answers") or {})
    explicit_limit = extract_admin_notification_limit(message)

    if _wants_list(message) and not _wants_explicit_summarize(message):
        answers["mode"] = "list"
        answers["attach_pdf"] = False
    elif _wants_explicit_summarize(message):
        answers["mode"] = "summarize"

    if explicit_limit is not None:
        answers["limit"] = explicit_limit

    return {**plan, "answers": answers}
