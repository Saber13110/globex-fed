"""Filtres transcript pour résumé Phase 4 — exclure le bruit technique."""

from __future__ import annotations

import re
import unicodedata

_BOILERPLATE_PATTERNS = (
    r"document pdf est pret",
    r"document pdf est prêt",
    r"votre export pdf",
    r"export pdf",
    r"lien de telechargement",
    r"lien de téléchargement",
    r"fichier excel est pret",
    r"fichier excel est prêt",
    r"your excel file is ready",
    r"export excel",
    r"download link below",
    r"utilisez le lien",
)


def _normalize_text(text: str) -> str:
    raw = (text or "").strip().lower()
    folded = unicodedata.normalize("NFKD", raw)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def _is_greeting_only(text: str) -> bool:
    norm = _normalize_text(text)
    if len(norm) > 120:
        return False
    greeting_markers = (
        "comment puis-je vous aider",
        "how can i help",
        "bonjour comment",
        "hello how can",
    )
    if not any(m in norm for m in greeting_markers):
        return False
    factual = ("colis", "suivi", "tracking", "fedex", "livraison", "export", "pdf", "excel")
    return not any(f in norm for f in factual)


def is_boilerplate_for_summary(text: str) -> bool:
    """True si le message assistant ne doit pas alimenter un résumé."""
    if not (text or "").strip():
        return True
    norm = _normalize_text(text)
    for pattern in _BOILERPLATE_PATTERNS:
        if re.search(pattern, norm, re.I):
            return True
    return _is_greeting_only(text)
