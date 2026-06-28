"""Chargement de la FAQ statique par langue."""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.support import FaqItem

_CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"

_LANG_FILES = {
    "fr": "faq_fr.json",
    "en": "faq_en.json",
    "ar": "faq_ar.json",
}


def normalize_faq_lang(code: str | None) -> str:
    raw = (code or "fr").strip().lower()[:2]
    return raw if raw in _LANG_FILES else "fr"


def load_faq(language: str | None) -> tuple[list[FaqItem], str]:
    lang = normalize_faq_lang(language)
    path = _CONTENT_DIR / _LANG_FILES[lang]
    if not path.is_file():
        path = _CONTENT_DIR / _LANG_FILES["fr"]
        lang = "fr"
    data = json.loads(path.read_text(encoding="utf-8"))
    items = [FaqItem.model_validate(row) for row in data if isinstance(row, dict)]
    return items, lang
