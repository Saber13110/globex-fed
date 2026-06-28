"""Filtre sortie LLM — supprime faux positifs « injection »."""

from __future__ import annotations

import re

_FALSE_INJECTION = re.compile(
    r"prompt\s*injection|cannot follow this instruction|tentative de prompt injection|"
    r"ressemble à une tentative|ne peux pas suivre cette instruction|instruction malveillante|"
    r"tentative d['']attaque",
    re.I,
)

_INJECTION_SENTENCE = re.compile(
    r"[^\n.!?]*(?:prompt\s*injection|cannot follow|ressemble à une tentative|"
    r"ne peux pas suivre cette instruction|instruction malveillante|tentative d['']attaque)[^\n.!?]*[.!?]?",
    re.I,
)

_FEDEX_LOOKUP_ERRORS = frozenset(
    {"sandbox_whitelist_denied", "fedex_not_found", "fedex_unavailable"}
)

_NOT_FOUND_FR = (
    "Je n'ai pas trouvé de colis correspondant à ce numéro de suivi. "
    "Vérifiez le numéro (12 à 14 chiffres) ou réessayez plus tard."
)
_NOT_FOUND_EN = (
    "I could not find a shipment for this tracking number. "
    "Please verify the number (12 to 14 digits) or try again later."
)


def sanitize_client_reply(
    reply: str,
    *,
    intent: str | None = None,
    fedex_error_code: str | None = None,
    ui_language: str | None = None,
) -> str:
    if not reply or intent in ("security_blocked",):
        return reply

    out = reply
    if fedex_error_code in _FEDEX_LOOKUP_ERRORS or intent in (
        "sandbox_whitelist_denied",
        "fedex_not_found",
        "track_package",
    ):
        if _FALSE_INJECTION.search(out):
            lang = (ui_language or "fr").lower()[:2]
            return _NOT_FOUND_EN if lang == "en" else _NOT_FOUND_FR

    if intent and not intent.startswith("security") and _FALSE_INJECTION.search(out):
        cleaned = _INJECTION_SENTENCE.sub("", out).strip()
        if cleaned:
            out = cleaned
        else:
            lang = (ui_language or "fr").lower()[:2]
            out = _NOT_FOUND_EN if lang == "en" and fedex_error_code else _NOT_FOUND_FR if fedex_error_code else out

    return out.strip() or reply
