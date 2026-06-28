"""Orchestration Ollama pour résumé de session — court / complet + repli factuel."""

from __future__ import annotations

import logging

from app.services.client_phase4.session_factual_summary import build_factual_summary_from_transcript
from app.services.client_phase4.session_summary_validator import (
    classify_transcript_content,
    is_acceptable_short_summary,
    is_acceptable_summary,
)
from app.services.client_phase4.transcript_filters import _normalize_text
from app.services.llm.providers import LlmProviderError, call_ollama_session_summary
from app.services.llm.prompts import language_lock_instruction

logger = logging.getLogger(__name__)

_RESUME_IMPOSSIBLE_TOKEN = "RESUME_IMPOSSIBLE"

_STRICT_SUMMARY_PROMPT_FR = (
    "Tu résumes une conversation PASSÉE entre un client et l'assistant FedEx Globex.\n"
    "RÈGLES STRICTES :\n"
    "- Résume UNIQUEMENT le transcript fourni, au PASSÉ (ce qui s'est dit).\n"
    "- 4 à 6 phrases factuelles sur les sujets abordés et les numéros de suivi cités.\n"
    "- INTERDIT : salutations, expliquer ce que tu peux faire, proposer de l'aide, parler au futur.\n"
    "- INTERDIT : PDF, Excel, liens de téléchargement.\n"
    "- Ne jamais inventer de statut colis, date ou localisation.\n"
    "- Ne recopie pas une phrase du transcript mot pour mot.\n"
    f"- Si le transcript ne permet pas un résumé fiable, réponds exactement : {_RESUME_IMPOSSIBLE_TOKEN}\n"
)

_STRICT_SUMMARY_PROMPT_EN = (
    "You summarize a PAST conversation between a client and the FedEx Globex assistant.\n"
    "STRICT RULES:\n"
    "- Summarize ONLY the provided transcript, in the PAST tense.\n"
    "- 4 to 6 factual sentences about topics and tracking numbers mentioned.\n"
    "- FORBIDDEN: greetings, explaining what you can do, offering help, future tense.\n"
    "- FORBIDDEN: PDF, Excel, download links.\n"
    "- Never invent shipment status, dates, or locations.\n"
    "- Do not copy a transcript line verbatim.\n"
    f"- If the transcript cannot support a reliable summary, reply exactly: {_RESUME_IMPOSSIBLE_TOKEN}\n"
)

_SHORT_SUMMARY_PROMPT_FR = (
    "Tu résumes une conversation PASSÉE très courte.\n"
    "- 1 à 2 phrases au passé, uniquement d'après le transcript.\n"
    "- INTERDIT : salutations, pitch de capacités, refuser l'accès à l'historique.\n"
)

_SHORT_SUMMARY_PROMPT_EN = (
    "You summarize a very short PAST conversation.\n"
    "- 1 to 2 past-tense sentences based ONLY on the transcript.\n"
    "- FORBIDDEN: greetings, capability pitch, refusing access to history.\n"
)


def _strict_system_prompt(lang: str) -> str:
    base = _STRICT_SUMMARY_PROMPT_EN if lang == "en" else _STRICT_SUMMARY_PROMPT_FR
    return f"{base}\n{language_lock_instruction(lang)}"


def _short_system_prompt(lang: str) -> str:
    base = _SHORT_SUMMARY_PROMPT_EN if lang == "en" else _SHORT_SUMMARY_PROMPT_FR
    return f"{base}\n{language_lock_instruction(lang)}"


def _is_resume_impossible_response(text: str) -> bool:
    norm = _normalize_text(text)
    return _RESUME_IMPOSSIBLE_TOKEN.lower().replace("_", "") in norm.replace("_", "")


def _factual_fallback(
    transcript: str,
    session_title: str,
    lang: str,
    *,
    tier: str = "short",
) -> str:
    factual = build_factual_summary_from_transcript(
        transcript,
        session_title=session_title,
        lang=lang,
        tier="full" if tier == "full" else "short",
    )
    if factual.strip():
        return factual
    raise LlmProviderError("summary_quality")


def _summarize_short(transcript: str, *, session_title: str, lang: str) -> str:
    title = session_title or "Conversation"
    try:
        raw = call_ollama_session_summary(
            transcript,
            session_title=title,
            ui_language=lang,
            system_prompt=_short_system_prompt(lang),
        )
        candidate = (raw or "").strip()
        if candidate and not _is_resume_impossible_response(candidate):
            if is_acceptable_short_summary(candidate, transcript, session_title=title):
                return candidate
    except LlmProviderError:
        logger.warning("short session summary Ollama failed, factual fallback", exc_info=True)
    return _factual_fallback(transcript, title, lang, tier="short")


def _summarize_full(transcript: str, *, session_title: str, lang: str) -> str:
    title = session_title or "Conversation"
    last_error: LlmProviderError | None = None

    for attempt, system_prompt in enumerate((None, _strict_system_prompt(lang)), start=1):
        try:
            raw = call_ollama_session_summary(
                transcript,
                session_title=title,
                ui_language=lang,
                system_prompt=system_prompt,
            )
        except LlmProviderError as exc:
            last_error = exc
            if attempt == 1:
                logger.warning("session summary Ollama attempt %s failed, retrying strict", attempt)
                continue
            logger.warning("session summary Ollama failed, factual fallback", exc_info=True)
            return _factual_fallback(transcript, title, lang, tier="full")

        candidate = (raw or "").strip()
        if _is_resume_impossible_response(candidate):
            logger.info("session summary attempt %s returned RESUME_IMPOSSIBLE", attempt)
            continue

        if is_acceptable_summary(candidate, transcript, session_title=title):
            return candidate

        logger.info(
            "session summary attempt %s rejected (len=%s)",
            attempt,
            len(candidate),
        )

    if last_error is not None:
        return _factual_fallback(transcript, title, lang, tier="full")
    return _factual_fallback(transcript, title, lang, tier="full")


def generate_session_summary(
    transcript: str,
    *,
    session_title: str,
    lang: str,
) -> str:
    """
    Ollama rédige le résumé selon le niveau de contenu (court / complet).
    Repli factuel si Ollama échoue ou si la validation rejette la sortie.
    """
    tier = classify_transcript_content(transcript)
    if tier == "empty":
        raise LlmProviderError("summary_insufficient_transcript")
    if tier == "short":
        return _summarize_short(transcript, session_title=session_title, lang=lang)
    return _summarize_full(transcript, session_title=session_title, lang=lang)
