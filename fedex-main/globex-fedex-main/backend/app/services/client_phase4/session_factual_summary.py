"""Résumé factuel depuis le transcript — sans LLM, sans inventer."""

from __future__ import annotations

import re
from typing import Literal

from app.services.client_phase4.session_summary_validator import extract_user_lines
from app.services.client_phase4.transcript_filters import _normalize_text

_TRACKING_RE = re.compile(r"\b\d{10,15}\b")
_FactualTier = Literal["short", "full"]


def _collect_tracking(transcript: str) -> list[str]:
    tracking: list[str] = []
    for ln in (transcript or "").splitlines():
        for tn in _TRACKING_RE.findall(ln):
            if tn not in tracking:
                tracking.append(tn)
    return tracking


def _dedupe_user_msgs(user_msgs: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for msg in user_msgs:
        key = _normalize_text(msg)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(msg.strip())
    return unique


def _user_line_to_sentence(msg: str, lang: str) -> str:
    text = (msg or "").strip()
    if not text:
        return ""
    lower = text.lower()
    if lang == "en":
        if any(w in lower for w in ("?", "where", "how", "what", "can you", "want")):
            return f"The user asked: {text}."
        return f"The user mentioned: {text}."
    if lang == "ar":
        return f"ذكر المستخدم: {text}."
    if any(w in lower for w in ("?", "où", "ou ", "comment", "quoi", "peux", "veux", "voudrais")):
        return f"L'utilisateur a demandé : {text}."
    return f"L'utilisateur a mentionné : {text}."


def _build_short_factual_summary(user_msgs: list[str], tracking: list[str], lang: str) -> str:
    bullets: list[str] = []
    if lang == "en":
        if len(user_msgs) == 1:
            bullets.append(f"The user asked: {user_msgs[0]}.")
        elif user_msgs:
            bullets.append(f"Main topics: {'; '.join(user_msgs[:3])}.")
        if tracking:
            bullets.append(f"Tracking numbers mentioned: {', '.join(tracking[:5])}.")
    elif lang == "ar":
        if user_msgs:
            bullets.append(f"مواضيع: {'; '.join(user_msgs[:3])}.")
        if tracking:
            bullets.append(f"أرقام التتبع: {', '.join(tracking[:5])}.")
    else:
        if len(user_msgs) == 1:
            bullets.append(f"L'utilisateur a demandé : {user_msgs[0]}.")
        elif user_msgs:
            bullets.append(f"Sujets abordés : {'; '.join(user_msgs[:3])}.")
        if tracking:
            bullets.append(f"Numéros de suivi mentionnés : {', '.join(tracking[:5])}.")
    return "\n".join(bullets)


def _build_full_factual_summary(user_msgs: list[str], tracking: list[str], lang: str) -> str:
    sentences: list[str] = []
    for msg in user_msgs[:5]:
        sentence = _user_line_to_sentence(msg, lang)
        if sentence:
            sentences.append(sentence)
    if tracking:
        joined = ", ".join(tracking[:5])
        if lang == "en":
            sentences.append(f"Tracking numbers {joined} were mentioned.")
        elif lang == "ar":
            sentences.append(f"تم ذكر أرقام التتبع: {joined}.")
        else:
            sentences.append(f"Les numéros de suivi {joined} ont été mentionnés.")
    return "\n".join(sentences)


def build_factual_summary_from_transcript(
    transcript: str,
    *,
    session_title: str,
    lang: str,
    tier: _FactualTier = "short",
) -> str:
    """Extrait sujets utilisateur et numéros de suivi — pas de citation bot."""
    _ = session_title
    user_msgs = _dedupe_user_msgs(extract_user_lines(transcript))
    tracking = _collect_tracking(transcript)

    if not user_msgs and not tracking:
        return ""

    if tier == "full":
        return _build_full_factual_summary(user_msgs, tracking, lang)
    return _build_short_factual_summary(user_msgs, tracking, lang)
