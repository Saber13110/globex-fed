"""Génération de titres de conversation (style ChatGPT)."""

from __future__ import annotations

import re

from app.services.llm.prompts import TITLE_GENERATION_PROMPT
from app.services.llm.providers import normalize_lang_code

DEFAULT_SESSION_TITLES = frozenset(
    {
        "",
        "conversation",
        "nouvelle conversation",
        "new conversation",
        "محادثة جديدة",
    }
)

_TITLE_PREFIX_RE = re.compile(
    r"^(titre|title|sujet|subject)\s*[:：\-]\s*",
    re.IGNORECASE,
)

_WEAK_TITLES = frozenset(
    {
        "fed",
        "fedex",
        "bonjour",
        "hello",
        "hi",
        "salut",
        "hey",
        "chat",
        "conversation",
        "question",
        "aide",
        "help",
        "assistant",
        "tracking",
        "suivi",
        "colis",
        "package",
    }
)


def should_auto_rename(title: str | None) -> bool:
    if not title or not title.strip():
        return True
    return title.strip().lower() in DEFAULT_SESSION_TITLES


def is_acceptable_title(title: str) -> bool:
    """Rejette les titres trop courts ou trop génériques (ex. « Fed », « FedEx »)."""
    t = title.strip()
    if len(t) < 8:
        return False
    normalized = t.lower().strip(" .-–—")
    if normalized in _WEAK_TITLES:
        return False
    words = [w for w in re.split(r"\s+", normalized) if w]
    if len(words) < 2:
        return False
    if len(words) == 2 and words[0] in _WEAK_TITLES:
        return False
    return True


def sanitize_session_title(raw: str, *, max_len: int = 56) -> str:
    """Nettoie la sortie LLM ou heuristique."""
    t = raw.strip().strip('"\'«»“”').replace("\n", " ")
    t = _TITLE_PREFIX_RE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" .-–—")
    if not t:
        return ""
    words = t.split()
    if len(words) > 8:
        t = " ".join(words[:8])
    if len(t) > max_len:
        cut = t[:max_len]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        t = cut.rstrip(" .-")
    return t or ""


def heuristic_session_title(
    user_message: str,
    *,
    ui_language: str | None = None,
    intent: str | None = None,
    tracking_number: str | None = None,
    has_image: bool = False,
) -> str:
    """Titre instantané à partir du message utilisateur (secours)."""
    lang = normalize_lang_code(ui_language)
    tn = (tracking_number or "").strip()

    if has_image and not (user_message or "").strip():
        if lang == "en":
            return "FedEx image analysis"
        if lang == "ar":
            return "تحليل صورة FedEx"
        return "Analyse image FedEx"

    if intent == "track_package" and tn:
        if lang == "en":
            return sanitize_session_title(f"FedEx tracking {tn}") or "Package tracking"
        if lang == "ar":
            return sanitize_session_title(f"تتبع شحنة {tn}") or "تتبع الشحنة"
        return sanitize_session_title(f"Suivi colis {tn}") or "Suivi de colis"

    if intent and "export" in (intent or "").lower():
        if lang == "en":
            return "FedEx history export"
        if lang == "ar":
            return "تصدير سجل الشحنات"
        return "Export historique FedEx"

    line = user_message.strip().split("\n")[0].strip()
    line = re.sub(r"\s+", " ", line)
    if not line:
        if lang == "en":
            return "New chat"
        if lang == "ar":
            return "محادثة جديدة"
        return "Nouvelle conversation"

    words = line.split()
    if len(words) > 6:
        line = " ".join(words[:6])
    title = sanitize_session_title(line)
    if title and is_acceptable_title(title):
        return title

    if lang == "en":
        return "FedEx support chat"
    if lang == "ar":
        return "محادثة دعم FedEx"
    return "Assistance suivi FedEx"


def build_title_user_prompt(
    user_message: str,
    *,
    bot_reply: str | None = None,
) -> str:
    """Prompt utilisateur pour Gemini (sujet = message utilisateur)."""
    user = user_message.strip()[:600]
    parts = [f"Premier message de l'utilisateur :\n{user}"]
    if bot_reply and bot_reply.strip():
        snippet = bot_reply.strip()[:280]
        parts.append(
            "Contexte (réponse courte de l'assistant — pour comprendre le sujet, ne pas recopier) :\n"
            f"{snippet}"
        )
    parts.append(
        "Génère le titre de la conversation pour la barre latérale (style ChatGPT)."
    )
    return "\n\n".join(parts)
