"""Reformulation LLM grounded — agent utilisateurs admin."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import get_settings
from app.services.admin_client.users.users_compose import compose_users_response
from app.services.admin_client.users.users_types import UsersPlan
from app.services.llm.providers import LlmProviderError, call_ollama_session_summary

logger = logging.getLogger(__name__)

_META_RE = re.compile(
    r"\b(introduction professionnelle|voici une|je suis le|i am the|bonjour)\b",
    re.I,
)


def _collect_tokens(obj: Any, tokens: set[str]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        tokens.add(str(int(obj)))
        return
    if isinstance(obj, str):
        for part in re.findall(r"[\w@.+-]+", obj):
            if len(part) > 2:
                tokens.add(part.lower())
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_tokens(v, tokens)
    elif isinstance(obj, list):
        for v in obj:
            _collect_tokens(v, tokens)


def _validate_grounded(reply: str, processed: dict[str, Any]) -> bool:
    if not reply or _META_RE.search(reply):
        return False
    allowed: set[str] = set()
    _collect_tokens(processed, allowed)
    for email in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", reply):
        if email.lower() not in allowed:
            return False
    user = processed.get("user") or processed.get("permissions") or {}
    expected_email = str(user.get("email") or "").strip()
    if expected_email and expected_email.lower() not in reply.lower():
        return False
    return True


def generate_users_answer_with_llm(
    message: str,
    processed: dict[str, Any],
    plan: UsersPlan,
    *,
    lang: str = "fr",
) -> tuple[str, str | None]:
    deterministic = compose_users_response(processed, plan, lang=lang, include_footer=False)
    settings = get_settings()
    if not settings.llm_enabled:
        return deterministic, None

    prompt = (
        "Reformule en français naturel la réponse admin suivante. "
        "Règles : ne change aucun email, id, rôle ou statut ; n'invente rien ; "
        "pas de salutation ; pas de mention de source technique.\n\n"
        f"DEMANDE : {message}\n\nDONNÉES :\n{deterministic}"
        if lang == "fr"
        else "Rephrase naturally. Do not change emails, ids, roles, or statuses.\n\n"
        f"REQUEST: {message}\n\nDATA:\n{deterministic}"
    )
    try:
        raw = call_ollama_session_summary(
            prompt,
            session_title="Users",
            ui_language=lang,
        )
        text = (raw or "").strip()
        if text and _validate_grounded(text, processed):
            return text, "ollama"
    except (LlmProviderError, TypeError, ValueError) as exc:
        logger.warning("users_narrative failed: %s", exc)
    return deterministic, None
