"""Extraction déterministe d'une référence conversation depuis le message utilisateur."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_LIST_INDEX_AFTER_COLON = re.compile(
    r"(?:conversation|discussion|échange|echange|chat)\s*:\s*(\d{1,2})\s*[.)]\s*",
    re.I,
)
_LIST_INDEX_INLINE = re.compile(
    r"(?:^|[\s:])((?:\d{1,2}))\s*[.)]\s+([^\n·]+)",
    re.I,
)
_SESSION_ID = re.compile(r"(?:session|id)\s*[=:]?\s*(\d+)", re.I)
_DATE_SUFFIX = re.compile(r"\s*·\s*\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}:\d{2})?\s*$")
_DATE_EXTRACT = re.compile(
    r"·\s*(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?",
)
_TITLE_DOT_DATE = re.compile(
    r"(?:^|[\s,])([^\n·]+?)\s*·\s*\d{1,2}/\d{1,2}/\d{4}",
    re.I,
)
_TIME_ONLY_EXTRACT = re.compile(r"·\s*(\d{1,2}):(\d{2})(?!\s*/\d)")
_TITLE_DOT_TIME = re.compile(
    r"(?:^|[\s,])([^\n·]+?)\s*·\s*\d{1,2}:\d{2}\b",
    re.I,
)
_ORDINAL_SELECTION = re.compile(
    r"\b(?:la|le|numero|numéro|n°|#)\s*(\d{1,2})\s*(?:e|er|ème|eme|ere|ère)?\b",
    re.I,
)
_DIGIT_ONLY = re.compile(r"^\s*(\d{1,2})\s*$")
_NARRATIVE_PREFIX = re.compile(
    r"^(?:depuis\s+le\s+titre|trouve(?:r)?\s+la\s+conversation|"
    r"cette\s+conversation|resume(?:r)?\s+(?:de\s+)?(?:cette\s+)?conversation)\s*[,:]?\s*",
    re.I,
)
_NARRATIVE_SUFFIX = re.compile(
    r"\s*(?:depuis\s+le\s+titre|et\s+la\s+date|que\s+je\s+fournis|"
    r"trouve(?:r)?\s+la\s+conversation|dis[- ]?moi|de\s+quoi\s+(?:elle\s+)?parle|"
    r"de\s+quoi\s+(?:on\s+)?(?:a\s+)?parl[eé]).*$",
    re.I,
)
_PURE_LIST_PHRASE = re.compile(
    r"^(?:donne(?:r)?(?:\s*-?\s*moi)?|montre(?:r|z)?|affiche(?:r|z)?|voir|quelles?)\s+"
    r"(?:les\s+|mes\s+)?(?:conversations?|discussions?|chats?)\s*(?:recent(?:e|es|s)?)?\s*$",
    re.I,
)


def _clean_title_hint(raw: str) -> str:
    text = (raw or "").strip()
    text = _DATE_SUFFIX.sub("", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def _strip_narrative_from_hint(raw: str) -> str:
    text = (raw or "").strip()
    text = _NARRATIVE_PREFIX.sub("", text).strip()
    text = _NARRATIVE_SUFFIX.sub("", text).strip()
    return text


def _parse_updated_hint(text: str) -> datetime | None:
    match = _DATE_EXTRACT.search(text or "")
    if not match:
        return None
    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))
    hour = int(match.group(4)) if match.group(4) else 0
    minute = int(match.group(5)) if match.group(5) else 0
    try:
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_summarize_selection(message: str) -> int | None:
    """Extrait un index de liste depuis un choix court (ex. la 5eme, 5)."""
    text = (message or "").strip()
    if not text:
        return None

    digit_only = _DIGIT_ONLY.match(text)
    if digit_only:
        idx = int(digit_only.group(1))
        return idx if idx > 0 else None

    ordinal = _ORDINAL_SELECTION.search(text)
    if ordinal:
        idx = int(ordinal.group(1))
        return idx if idx > 0 else None

    compact = re.search(r"\b(\d{1,2})\s*(?:e|er|ème|eme|ere|ère)\b", text, re.I)
    if compact:
        idx = int(compact.group(1))
        return idx if idx > 0 else None

    return None


def _parse_time_hint(text: str) -> tuple[int, int] | None:
    if _DATE_EXTRACT.search(text or ""):
        return None
    match = _TIME_ONLY_EXTRACT.search(text or "")
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def _extract_hint_from_title_dot_time(text: str) -> str | None:
    if not _TIME_ONLY_EXTRACT.search(text or ""):
        return None
    match = _TITLE_DOT_TIME.search(text)
    if not match:
        return None
    segment = _strip_narrative_from_hint(match.group(1))
    hint = _clean_title_hint(segment)
    if len(hint) < 3:
        return None
    if _PURE_LIST_PHRASE.match(hint):
        return None
    return hint


def _extract_hint_from_title_dot_date(text: str) -> str | None:
    if not _DATE_EXTRACT.search(text or ""):
        return None
    match = _TITLE_DOT_DATE.search(text)
    if not match:
        return None
    segment = _strip_narrative_from_hint(match.group(1))
    hint = _clean_title_hint(segment)
    if len(hint) < 3:
        return None
    if _PURE_LIST_PHRASE.match(hint):
        return None
    return hint


def parse_session_reference(message: str) -> dict[str, Any]:
    """
    Extrait list_index, session_hint, session_id et date depuis le message brut.
    Complète le plan LLM — ne remplace pas le routeur.
    """
    text = (message or "").strip()
    result: dict[str, Any] = {
        "list_index": None,
        "session_hint": None,
        "session_id": None,
        "session_updated_hint": None,
        "session_time_hint": None,
    }
    if not text:
        return result

    result["session_updated_hint"] = _parse_updated_hint(text)
    if result["session_updated_hint"] is None:
        result["session_time_hint"] = _parse_time_hint(text)

    sid_match = _SESSION_ID.search(text)
    if sid_match:
        try:
            result["session_id"] = int(sid_match.group(1))
        except ValueError:
            pass

    colon_match = _LIST_INDEX_AFTER_COLON.search(text)
    if colon_match:
        try:
            result["list_index"] = int(colon_match.group(1))
        except ValueError:
            pass
        hint = _clean_title_hint(colon_match.group(0).split(":", 1)[-1])
        hint = re.sub(r"^\d{1,2}\s*[.)]\s*", "", hint).strip()
        if hint:
            result["session_hint"] = hint

    inline_match = _LIST_INDEX_INLINE.search(text)
    if inline_match and result["list_index"] is None:
        try:
            result["list_index"] = int(inline_match.group(1))
        except ValueError:
            pass
        hint = _clean_title_hint(inline_match.group(2))
        if hint and not result["session_hint"]:
            result["session_hint"] = hint

    if result["list_index"] is None:
        selection = parse_summarize_selection(text)
        if selection is not None:
            result["list_index"] = selection

    if result["session_hint"] is None:
        title_hint = _extract_hint_from_title_dot_date(text)
        if title_hint:
            result["session_hint"] = title_hint

    if result["session_hint"] is None:
        title_time_hint = _extract_hint_from_title_dot_time(text)
        if title_time_hint:
            result["session_hint"] = title_time_hint

    if result["session_hint"] is None:
        conv_colon = re.search(
            r"(?:conversation|discussion|échange|echange|chat|résumé|resume)\s*:\s*(.+)$",
            text,
            re.I,
        )
        if conv_colon:
            after = conv_colon.group(1).strip()
            after = re.sub(r"^\d{1,2}\s*[.)]\s*", "", after).strip()
            hint = _clean_title_hint(after)
            if len(hint) >= 3 and not _PURE_LIST_PHRASE.match(hint):
                result["session_hint"] = hint

    return result


def _has_explicit_target(ref: dict[str, Any]) -> bool:
    return bool(ref.get("list_index") or ref.get("session_hint") or ref.get("session_id"))


def enrich_summarize_answers(message: str, answers: dict[str, Any]) -> dict[str, Any]:
    """
    Fusionne answers LLM avec le parsing message.
    Le parsing message est prioritaire si le LLM n'a pas fourni de cible explicite.
    """
    merged = dict(answers or {})
    ref = parse_session_reference(message)

    for key in ("list_index", "session_hint", "session_id", "session_updated_hint", "session_time_hint"):
        parsed = ref.get(key)
        if parsed is None:
            continue
        llm_val = merged.get(key)
        if llm_val is None or llm_val == "":
            merged[key] = parsed
        elif key == "list_index":
            try:
                if int(llm_val) != int(parsed):
                    merged[key] = parsed
            except (TypeError, ValueError):
                merged[key] = parsed

    if _has_explicit_target(ref) or _has_explicit_target(merged):
        scope = str(merged.get("scope") or "").strip().lower()
        if scope == "current" and _has_explicit_target(ref):
            merged.pop("scope", None)

    text = (message or "").strip().lower()
    if any(
        w in text
        for w in (
            "cette conversation",
            "notre conversation",
            "cette discussion",
            "cet échange",
            "ici",
            "actuelle",
        )
    ):
        if not _has_explicit_target(ref):
            merged["scope"] = "current"

    if not merged.get("scope") and not _has_explicit_target(merged):
        if any(w in text for w in ("dernière", "derniere", "récente", "recente")):
            merged["scope"] = "last"

    return merged
