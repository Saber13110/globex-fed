"""Détection d'intention minimale (fr / en / ar)."""

from __future__ import annotations

import re

from app.services.llm.tracking_extract import extract_tracking_number

# Mots-clés liés au suivi de colis
_TRACK_KEYWORDS: tuple[str, ...] = (
    # Français
    "suivi",
    "suivre",
    "colis",
    "numéro de suivi",
    "numero de suivi",
    "tracking",
    "track",
    "package",
    "shipment",
    "parcel",
    "fedex",
    "où est",
    "ou est",
    "statut",
    "preuve de livraison",
    # Anglais
    "delivered",
    "proof of delivery",
    "in transit",
    "transit",
    # Arabe (formes courantes)
    "تتبع",
    "طرد",
    "شحنة",
    "فيديكس",
    "qui a reçu",
    "qui a recu",
    "derniers événements",
    "derniers evenements",
    "a-t-il été livré",
    "ete livre",
    "destinataire",
)

_GENERAL_LOGISTICS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(combien|how long|how many|how much|quelle est la durée|quel délai|quel delai)\b", re.I),
    re.compile(r"\b(généralement|generalement|en moyenne|habituellement|typically|usually|en général|en general)\b", re.I),
    re.compile(r"\b\d+\s*(km|kilomètres|kilometres|kilometer|kilometers|miles)\b", re.I),
    re.compile(r"\b(c'est quoi|qu'est-ce que|what is|explain|explique|pourquoi)\b", re.I),
    re.compile(r"\b(comment ça marche|comment ca marche|how does|différence|difference)\b", re.I),
    re.compile(r"\b(tarif|prix|coût|cout|price|cost|service fedex)\b", re.I),
)

_OFF_TOPIC_GEO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(distance|distances)\b", re.I),
    re.compile(r"\b(entre|between)\s+.+\s+(et|and)\s+", re.I),
    re.compile(r"\b(kilomètre|kilometre|kilometer|kilometers|km)\b", re.I),
    re.compile(r"\b(géograph|geograph|géographie|geographie|geography)\b", re.I),
    re.compile(r"\b(pays|country|countries|continent)\b", re.I),
    re.compile(r"\b(capital|capitale|frontière|frontiere|border)\b", re.I),
)

_INTENT_TRACK = "track_package"
_INTENT_GENERAL = "general_question"


def is_off_topic_general_question(message: str) -> bool:
    """Question hors logistique / suivi (géo, distance entre pays, etc.)."""
    if extract_tracking_number(message):
        return False
    text = (message or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _OFF_TOPIC_GEO_PATTERNS)


def is_general_logistics_question(message: str) -> bool:
    """Question générale logistique / FedEx sans numéro de suivi précis."""
    if extract_tracking_number(message):
        return False
    if is_off_topic_general_question(message):
        return True
    text = (message or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _GENERAL_LOGISTICS_PATTERNS)


def detect_intent(message: str, tracking_number: str | None = None) -> str:
    """
    Si un numéro de suivi plausible est présent → track_package.
    Questions générales (délais, km, « en général ») → general_question.
    Sinon mots-clés de suivi ponctuel → track_package.
    """
    if is_general_logistics_question(message):
        return _INTENT_GENERAL

    if tracking_number and tracking_number.strip():
        from app.utils.tracking_parser import is_plausible_tracking_number

        if is_plausible_tracking_number(tracking_number):
            return _INTENT_TRACK

    text = message.strip().lower()
    if not text:
        return _INTENT_GENERAL

    if any(keyword in text for keyword in _TRACK_KEYWORDS):
        return _INTENT_TRACK

    if re.search(r"\b(track|suiv|ship|deliver|livré|livree|livraison)\w*", text, re.IGNORECASE):
        if re.search(r"\b(mon colis|my package|ce colis|this package|numéro|numero|#\d)\b", text, re.I):
            return _INTENT_TRACK

    return _INTENT_GENERAL
