"""Knowledge base articles for the Help Center."""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.help import HelpArticle, HelpArticleSummary

_CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"

_LANG_FILES = {
    "fr": "help_articles_fr.json",
    "en": "help_articles_en.json",
    "ar": "help_articles_ar.json",
}


def normalize_lang(code: str | None) -> str:
    raw = (code or "fr").strip().lower()[:2]
    return raw if raw in _LANG_FILES else "fr"


def _load_raw(lang: str) -> list[dict]:
    path = _CONTENT_DIR / _LANG_FILES[lang]
    if not path.is_file():
        path = _CONTENT_DIR / _LANG_FILES["en"]
    data = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in data if isinstance(row, dict)]


def list_help_articles(lang: str | None = None) -> list[HelpArticleSummary]:
    resolved = normalize_lang(lang)
    articles = _load_raw(resolved)
    return [
        HelpArticleSummary.model_validate(
            {k: a[k] for k in ("id", "slug", "title", "category", "summary", "readTime", "updatedAt")}
        )
        for a in articles
    ]


def get_help_article(slug: str, lang: str | None = None) -> HelpArticle | None:
    resolved = normalize_lang(lang)
    for row in _load_raw(resolved):
        if row.get("slug") == slug:
            return HelpArticle.model_validate(row)
    return None
