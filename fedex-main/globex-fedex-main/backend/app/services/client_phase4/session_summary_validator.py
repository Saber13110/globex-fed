"""Validation de la sortie Ollama pour résumé session — anti hors-sujet."""

from __future__ import annotations

import re
from typing import Literal

from app.services.client_phase4.transcript_filters import _normalize_text, is_boilerplate_for_summary

TranscriptTier = Literal["empty", "short", "full"]

_SYNTHESIS_MARKERS = (
    "resume",
    "resumé",
    "sujet",
    "abord",
    "discut",
    "mention",
    "demand",
    "question",
    "tracking",
    "colis",
    "suivi",
    "conversation",
    "echange",
    "échange",
)

_PAST_TENSE_MARKERS = (
    "a demande",
    "a demandé",
    "a parle",
    "a parlé",
    "avait",
    "l'utilisateur",
    "l utilisateur",
    "the user",
    "during this",
    "dans cette conversation",
    "during the",
    "mentioned",
    "asked about",
)

_CAPABILITY_PITCH_MARKERS = (
    "je peux suivre",
    "i can track",
    "je peux aussi repondre",
    "je peux aussi répondre",
    "i can also answer",
    "veuillez me donner",
    "please give me more",
    "nos services",
    "shipping services",
    "services d'expedition",
    "services d'expédition",
)

_META_REFUSAL_MARKERS = (
    "ne peux pas acceder",
    "ne peux pas accéder",
    "cannot access",
    "can't access",
    "conversations precedentes",
    "conversations précédentes",
    "previous conversations",
    "pouvez-vous me dire ce qui se passe",
    "can you tell me what",
    "pas acces a l historique",
    "pas accès à l'historique",
    "do not have access",
    "don't have access",
)

_GREETING_START = re.compile(
    r"^\s*(bonjour|salut|hello|hi)\b",
    re.I,
)

_TRACKING_RE = re.compile(r"\b\d{10,15}\b")

_STOPWORDS = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "de",
        "du",
        "et",
        "en",
        "a",
        "the",
        "and",
        "to",
        "for",
        "is",
        "was",
        "mon",
        "mes",
        "votre",
        "vos",
        "je",
        "tu",
        "il",
        "elle",
        "nous",
        "vous",
        "ils",
        "que",
        "qui",
        "dans",
        "sur",
        "avec",
        "pour",
        "par",
        "conversations",
        "conversation",
        "liste",
        "recentes",
        "recents",
        "tous",
        "toutes",
        "moi",
        "tous les",
    }
)

_SHORT_MIN_CHARS = 25
_FULL_MIN_CHARS = 80


def _token_overlap_ratio(a: str, b: str) -> float:
    ta = set(_normalize_text(a).split())
    tb = set(_normalize_text(b).split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _significant_tokens(text: str) -> set[str]:
    tokens = _normalize_text(text).split()
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def extract_user_lines(transcript: str) -> list[str]:
    lines: list[str] = []
    for ln in (transcript or "").splitlines():
        if ln.strip().lower().startswith("utilisateur:"):
            lines.append(ln.split(":", 1)[-1].strip())
    return [ln for ln in lines if ln]


def user_content_char_count(transcript: str) -> int:
    return len(" ".join(extract_user_lines(transcript)).strip())


def classify_transcript_content(transcript: str) -> TranscriptTier:
    user_lines = extract_user_lines(transcript)
    if not user_lines:
        return "empty"
    char_count = user_content_char_count(transcript)
    if char_count < _SHORT_MIN_CHARS:
        return "empty"
    if char_count < _FULL_MIN_CHARS:
        return "short"
    return "full"


def has_sufficient_user_content(transcript: str, *, min_chars: int = 80) -> bool:
    return user_content_char_count(transcript) >= min_chars


def _assistant_lines(transcript: str) -> list[str]:
    lines: list[str] = []
    for ln in (transcript or "").splitlines():
        if ln.strip().lower().startswith("assistant:"):
            lines.append(ln.split(":", 1)[-1].strip())
    return lines


def _is_greeting_without_substance(summary: str) -> bool:
    text = (summary or "").strip()
    if not text:
        return True
    if not _GREETING_START.match(text):
        return False
    norm = _normalize_text(text)
    if len(norm) < 40:
        return True
    return not any(m in norm for m in _SYNTHESIS_MARKERS)


def _is_capability_pitch(summary: str) -> bool:
    norm = _normalize_text(summary)
    if any(marker in norm for marker in _CAPABILITY_PITCH_MARKERS):
        return True
    if "delais de livraison" in norm or "délais de livraison" in norm:
        if not any(m in norm for m in _PAST_TENSE_MARKERS):
            return True
    return False


def _is_meta_refusal(summary: str) -> bool:
    norm = _normalize_text(summary)
    return any(marker in norm for marker in _META_REFUSAL_MARKERS)


def _is_title_echo_only(summary: str, session_title: str) -> bool:
    if not session_title:
        return False
    norm_summary = _normalize_text(summary)
    norm_title = _normalize_text(session_title)
    if not norm_title or len(norm_summary) < 10:
        return False
    if any(m in norm_summary for m in _PAST_TENSE_MARKERS):
        return False
    overlap = _token_overlap_ratio(summary, session_title)
    if overlap >= 0.75 and len(norm_summary) <= len(norm_title) + 30:
        return True
    if norm_summary == norm_title or norm_title in norm_summary:
        return True
    return False


def has_transcript_anchor(summary: str, transcript: str) -> bool:
    user_lines = extract_user_lines(transcript)
    if not user_lines:
        return True

    norm_summary = _normalize_text(summary)
    if any(m in norm_summary for m in _PAST_TENSE_MARKERS):
        return True

    summary_tracking = set(_TRACKING_RE.findall(summary or ""))
    transcript_tracking = set(_TRACKING_RE.findall(transcript or ""))
    if summary_tracking & transcript_tracking:
        return True

    summary_tokens = _significant_tokens(summary)
    if not summary_tokens:
        return False

    for user_line in user_lines:
        user_tokens = _significant_tokens(user_line)
        if not user_tokens:
            continue
        overlap = len(summary_tokens & user_tokens)
        if overlap >= 3:
            return True

    return False


def is_acceptable_summary(
    summary: str,
    transcript: str,
    *,
    session_title: str = "",
) -> bool:
    """False si la sortie ressemble à du boilerplate ou une copie du transcript."""
    text = (summary or "").strip()
    if not text or len(text) < 20:
        return False
    if "resume_impossible" in _normalize_text(text):
        return False
    if is_boilerplate_for_summary(text):
        return False
    if _is_greeting_without_substance(text):
        return False
    if _is_capability_pitch(text):
        return False
    if _is_meta_refusal(text):
        return False
    if session_title and _is_title_echo_only(text, session_title):
        return False
    for assistant_line in _assistant_lines(transcript):
        if len(assistant_line) < 30:
            continue
        if _token_overlap_ratio(text, assistant_line) >= 0.85:
            return False
    if extract_user_lines(transcript) and not has_transcript_anchor(text, transcript):
        return False
    return True


def is_acceptable_short_summary(
    summary: str,
    transcript: str,
    *,
    session_title: str = "",
) -> bool:
    """Validation allégée pour sessions courtes — pas pitch, pas meta-refus."""
    text = (summary or "").strip()
    if not text or len(text) < 10:
        return False
    if "resume_impossible" in _normalize_text(text):
        return False
    if is_boilerplate_for_summary(text):
        return False
    if _is_capability_pitch(text):
        return False
    if _is_meta_refusal(text):
        return False
    if session_title and _is_title_echo_only(text, session_title):
        return False
    if extract_user_lines(transcript) and not has_transcript_anchor(text, transcript):
        return False
    return True
