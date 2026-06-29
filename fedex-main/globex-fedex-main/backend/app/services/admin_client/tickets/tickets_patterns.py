"""Patterns partagés tickets — workspace et intent utilisent les mêmes signaux."""

from __future__ import annotations

import re
import unicodedata

# Liste / « tous les tickets » — formulations naturelles admin
TICKETS_LIST_UTTERANCE_RE = re.compile(
    r"\b("
    r"liste.{0,45}tickets?|list.{0,45}tickets?|"
    r"donne.{0,45}tickets?|montre.{0,45}tickets?|affiche.{0,45}tickets?|"
    r"(tous les|all)\s+(les\s+)?tickets?|"
    r"tous\s+les\s+tickets?|"
    r"quels?\s+sont\s+les\s+tickets?|"
    r"je\s+veux.{0,30}tickets?"
    r")\b",
    re.I,
)

TICKETS_CATALOG_RE = re.compile(r"\btickets?\b", re.I)


def normalize_tickets_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def is_tickets_list_utterance(message: str) -> bool:
    return bool(TICKETS_LIST_UTTERANCE_RE.search(normalize_tickets_text(message)))


def score_tickets_utterance(message: str) -> float:
    """Score souple — seuil 2.0 pour engager le workspace."""
    norm = normalize_tickets_text(message)
    if is_tickets_list_utterance(message):
        return 3.0
    if re.search(r"\b(r[eé]sum[eé]|summary).{0,40}\btickets\b", norm, re.I):
        return 3.0
    if re.search(r"\b(d[eé]tails?|fiches?).{0,40}\btickets\b", norm, re.I):
        return 3.0
    if re.search(r"\b(fiche|d[eé]tail|infos?).{0,35}\bticket\b", norm, re.I):
        return 3.0
    if re.search(r"\bticket\s*#\s*\d+", norm, re.I):
        return 3.0
    if re.search(r"\btickets?\s+support|support\s+tickets?\b", norm, re.I):
        return 2.5
    if TICKETS_CATALOG_RE.search(norm):
        return 1.5
    return 0.0
