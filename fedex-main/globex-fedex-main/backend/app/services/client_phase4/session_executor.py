"""Exécution list_sessions et summarize_session."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.client_phase4.session_factual_summary import build_factual_summary_from_transcript
from app.services.client_phase4.session_service import (
    build_session_transcript,
    format_relative_sessions_header,
    format_session_line,
    list_user_sessions,
    resolve_session_target,
)
from app.services.client_phase4.session_summary_llm import generate_session_summary
from app.services.llm.providers import LlmProviderError

logger = logging.getLogger(__name__)

_EMPTY_LIST = {
    "fr": "Vous n'avez pas encore de conversation enregistrée.",
    "en": "You don't have any saved conversations yet.",
    "ar": "ليس لديك محادثات محفوظة بعد.",
}

_AMBIGUOUS = {
    "fr": "Plusieurs conversations correspondent. Laquelle souhaitez-vous résumer ?\n",
    "en": "Several conversations match. Which one should I summarize?\n",
    "ar": "عدة محادثات تطابق طلبك. أيها تريد تلخيصه؟\n",
}

_INVALID_INDEX = {
    "fr": "Je n'ai pas trouvé la conversation n°{index} dans votre liste récente. Demandez d'abord « montre mes conversations » ou précisez le titre.",
    "en": "I couldn't find conversation #{index} in your recent list. Ask to list conversations first or specify the title.",
    "ar": "لم أجد المحادثة رقم {index}. اطلب قائمة المحادثات أو حدد العنوان.",
}

_AUTO_SUMMARY_NOTE = {
    "fr": "(résumé automatique)",
    "en": "(automatic summary)",
    "ar": "(ملخص تلقائي)",
}

_SUMMARY_UNAVAILABLE = {
    "fr": "Je n'ai pas pu produire un résumé fiable pour « {title} » pour l'instant. Réessayez dans quelques secondes.",
    "en": "I couldn't produce a reliable summary for « {title} » right now. Please try again in a few seconds.",
    "ar": "لم أتمكن من إنتاج ملخص موثوق لـ « {title} » الآن. أعد المحاولة بعد قليل.",
}

_SUMMARY_INSUFFICIENT = {
    "fr": "Cette conversation ne contient pas assez d'échanges pour produire un résumé.",
    "en": "This conversation doesn't contain enough exchanges to produce a summary.",
    "ar": "لا تحتوي هذه المحادثة على تبادلات كافية لإنتاج ملخص.",
}


def _lang(ui_language: str | None, user: User) -> str:
    code = (ui_language or user.preferred_language or "fr").lower()[:2]
    return code if code in {"fr", "en", "ar"} else "fr"


def _summary_unavailable_message(session_title: str, lang: str) -> str:
    title = (session_title or "Conversation").strip()
    template = _SUMMARY_UNAVAILABLE.get(lang, _SUMMARY_UNAVAILABLE["fr"])
    return template.format(title=title)


def _summary_insufficient_message(lang: str) -> str:
    return _SUMMARY_INSUFFICIENT.get(lang, _SUMMARY_INSUFFICIENT["fr"])


def _summary_error_message(exc: LlmProviderError, session_title: str, lang: str) -> str:
    code = str(exc).strip().lower()
    if "summary_insufficient_transcript" in code:
        return _summary_insufficient_message(lang)
    return _summary_unavailable_message(session_title, lang)


def deterministic_session_summary(
    transcript: str,
    *,
    session_title: str,
    lang: str,
) -> str:
    """Repli factuel sans LLM — ne invente pas de statut colis."""
    factual = build_factual_summary_from_transcript(
        transcript,
        session_title=session_title,
        lang=lang,
    )
    note = _AUTO_SUMMARY_NOTE.get(lang, _AUTO_SUMMARY_NOTE["fr"])
    return f"{factual}\n\n{note}" if factual.strip() else note


def execute_list_sessions(
    db: Session,
    user: User,
    *,
    ui_language: str | None = None,
    assistant_intro: str = "",
) -> str:
    lang = _lang(ui_language, user)
    sessions = list_user_sessions(db, user_id=user.id)
    if not sessions:
        return _EMPTY_LIST.get(lang, _EMPTY_LIST["fr"])

    header = format_relative_sessions_header(lang)
    lines = [header, ""]
    if assistant_intro.strip():
        lines.insert(0, assistant_intro.strip())
        lines.insert(1, "")
    for i, s in enumerate(sessions, start=1):
        lines.append(format_session_line(s, index=i, lang=lang))
    return "\n".join(lines)


def execute_summarize_session(
    db: Session,
    user: User,
    *,
    current_session_id: int,
    answers: dict[str, Any],
    ui_language: str | None = None,
    assistant_intro: str = "",
) -> tuple[str, bool]:
    """Retourne (reply, needs_clarification)."""
    lang = _lang(ui_language, user)
    normalized = {
        "scope": answers.get("scope"),
        "session_hint": answers.get("session_hint"),
        "session_id": answers.get("session_id"),
        "list_index": answers.get("list_index"),
        "session_updated_hint": answers.get("session_updated_hint"),
        "session_time_hint": answers.get("session_time_hint"),
    }
    target, ambiguous, err = resolve_session_target(
        db,
        user_id=user.id,
        current_session_id=current_session_id,
        answers=normalized,
    )

    if err == "no_sessions":
        return _EMPTY_LIST.get(lang, _EMPTY_LIST["fr"]), False

    if err == "invalid_index":
        idx = normalized.get("list_index") or "?"
        msg = _INVALID_INDEX.get(lang, _INVALID_INDEX["fr"]).format(index=idx)
        return msg, True

    if err == "ambiguous" and ambiguous:
        prefix = _AMBIGUOUS.get(lang, _AMBIGUOUS["fr"])
        listing = "\n".join(
            format_session_line(s, index=i, lang=lang) for i, s in enumerate(ambiguous, start=1)
        )
        return prefix + listing, True

    if target is None:
        no_match = {
            "fr": "Je n'ai pas trouvé la conversation demandée. Précisez le titre ou choisissez dans la liste.",
            "en": "I couldn't find that conversation. Please specify the title or pick from the list.",
            "ar": "لم أجد المحادثة المطلوبة. حدد العنوان أو اختر من القائمة.",
        }
        return no_match.get(lang, no_match["fr"]), True

    transcript = build_session_transcript(db, session_id=target.id, for_summary=True)
    if not transcript.strip():
        empty = {
            "fr": f"La conversation « {target.title} » ne contient pas encore de messages.",
            "en": f"The conversation « {target.title} » has no messages yet.",
            "ar": f"المحادثة « {target.title} » لا تحتوي على رسائل بعد.",
        }
        return empty.get(lang, empty["fr"]), False

    try:
        summary = generate_session_summary(
            transcript,
            session_title=target.title or "Conversation",
            lang=lang,
        )
    except LlmProviderError as exc:
        logger.warning("summarize_session unavailable, honest fallback", exc_info=True)
        code = str(exc).strip().lower()
        if "summary_insufficient_transcript" in code:
            summary = _summary_insufficient_message(lang)
        else:
            factual = build_factual_summary_from_transcript(
                transcript,
                session_title=target.title or "Conversation",
                lang=lang,
            )
            summary = factual if factual.strip() else _summary_unavailable_message(
                target.title or "Conversation", lang
            )

    parts: list[str] = []
    if assistant_intro.strip():
        parts.append(assistant_intro.strip())
    title_line = f"**{target.title}**"
    parts.append(title_line)
    parts.append(summary.strip())
    return "\n\n".join(parts), False
