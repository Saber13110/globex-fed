"""Détection et gestion multilingue de l'assistant admin."""

from __future__ import annotations

import re

from app.services.gpt.memory_service import detect_language_preference
from app.services.llm.providers import normalize_lang_code

_SUPPORTED = frozenset({"fr", "en", "es", "ar", "de"})

_ES_WORDS = re.compile(
    r"\b(cuánt|cuant|notificaciones|usuarios|hola|gracias|por favor|"
    r"cuántos|cuantos|resumen|seguridad|tickets|conversaciones|"
    r"lista|responde|espanol|español)\b",
    re.I,
)
_DE_WORDS = re.compile(
    r"\b(benutzer|benachrichtigungen|wie viele|zusammenfassung|"
    r"sicherheit|protokolle|hallo|bitte|tracking)\b",
    re.I,
)
_EN_WORDS = re.compile(
    r"\b(how many|notifications|users|hello|please|summary|"
    r"security|logs|tickets|tracking|what are|show me)\b",
    re.I,
)
_FR_WORDS = re.compile(
    r"\b(combien|notifications|utilisateurs|bonjour|merci|"
    r"résumé|resumé|sécurité|securite|logs|tickets|"
    r"quels|donne|analyse|plateforme|suspectes|actions|colis|"
    r"y a-t-il|dernières|dernieres|heures|comptes|administrateur|"
    r"exporte|montre|actifs|fréquent|frequent|rapport|santé|sante|"
    r"où|ou est|historique|expéditeur|expediteur|maintenant)\b",
    re.I,
)


def detect_message_language(message: str) -> str:
    """Détecte la langue dominante du message (fr/en/es/ar/de)."""
    text = (message or "").strip()
    if not text:
        return "fr"
    if re.search(r"[\u0600-\u06FF]", text):
        return "ar"
    if re.search(r"[àâäéèêëïîôùûüç]", text, re.I):
        return "fr"
    if _ES_WORDS.search(text) or re.search(r"[¿¡]", text):
        # Ne pas classer ES si accents français ou mots FR dominants
        if not re.search(r"[àâäéèêëïîôùûüç]", text, re.I):
            fr_hits = len(_FR_WORDS.findall(text))
            if fr_hits == 0:
                return "es"
    if _DE_WORDS.search(text):
        return "de"
    fr_hits = len(_FR_WORDS.findall(text))
    en_hits = len(_EN_WORDS.findall(text))
    if en_hits > fr_hits and en_hits > 0:
        return "en"
    if fr_hits > 0:
        return "fr"
    if re.match(r"^(hello|hi|hey)\b", text, re.I):
        return "en"
    if re.match(r"^(hola|buenos)\b", text, re.I):
        return "es"
    return "fr"


def resolve_response_language(
    message: str,
    *,
    profile_language: str | None = None,
    session_language: str | None = None,
    memory_language: str | None = None,
) -> tuple[str, bool]:
    """
    Résout la langue de réponse.
    Retourne (code_langue, preference_updated).
    Priorité : demande explicite > mémoire session > mémoire long terme > détection > profil > fr.
    """
    explicit = detect_language_preference(message)
    if explicit:
        lang = normalize_lang_code(explicit)
        if lang in _SUPPORTED:
            return lang, True

    if session_language:
        lang = normalize_lang_code(session_language)
        if lang in _SUPPORTED:
            return lang, False

    if memory_language:
        lang = normalize_lang_code(memory_language)
        if lang in _SUPPORTED:
            return lang, False

    detected = detect_message_language(message)
    if detected in _SUPPORTED:
        return detected, False

    if profile_language:
        lang = normalize_lang_code(profile_language)
        if lang in _SUPPORTED:
            return lang, False

    return "fr", False


def language_label(code: str) -> str:
    labels = {
        "fr": "Français",
        "en": "English",
        "es": "Español",
        "ar": "العربية",
        "de": "Deutsch",
    }
    return labels.get(code, code)
