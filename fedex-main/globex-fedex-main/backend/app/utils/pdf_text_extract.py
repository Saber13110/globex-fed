"""Extraction de texte libre pour PDF depuis un message utilisateur."""

from __future__ import annotations

import re


def extract_custom_pdf_text(message: str) -> str | None:
    """Extrait le texte à mettre dans un PDF libre (ex. « pdf contient bonjour »)."""
    text = (message or "").strip()
    patterns = [
        r'["\'«]([^"\']{1,800})["\'»]',
        r"\bcontient\s+(.+?)(?:\s+dans|\s+en\s+pdf|\s*$)",
        r"\bcontenant\s+(.+?)(?:\s+dans|\s+en\s+pdf|\s*$)",
        r"\b(?:avec|ayant|texte|écrit|ecrit)\s+(.+?)(?:\s+dans|\s+en\s+pdf|\s*$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            body = m.group(1).strip().strip("\"'«»")
            if body:
                return body[:800]
    return None
