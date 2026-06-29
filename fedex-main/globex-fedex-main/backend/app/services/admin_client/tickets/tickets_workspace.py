"""Espace de travail tickets support admin — gate Jarvis."""

from __future__ import annotations

import re

from app.services.admin_client.tickets.tickets_followup import is_tickets_followup_message
from app.services.admin_client.tickets.tickets_patterns import (
    is_tickets_list_utterance,
    normalize_tickets_text,
    score_tickets_utterance,
)

_TICKETS_MGMT_RE = re.compile(
    r"\b("
    r"tickets?\s+support|support\s+tickets?|"
    r"tickets?\s+(ouverts?|open|pending|en\s+cours|r[eé]solus?|resolved|closed|ferm[eé]s?)|"
    r"r[eé]sum[eé].{0,35}tickets?|summary.{0,35}tickets?|"
    r"fiche\s+ticket|d[eé]tails?\s+(des\s+)?tickets?|d[eé]tail.{0,30}ticket|ticket\s+d[eé]tail|"
    r"tickets?\s+(du|de|pour)\s+|"
    r"ce\s+ticket|cet\s+ticket|cette\s+demande|"
    r"ticket\s*#|#\s*\d{1,8}.{0,20}ticket|"
    r"\b(TKT[-_]?|SUP-)\w+"
    r")\b",
    re.I,
)

_SHIPMENT_SUPPORT_RE = re.compile(
    r"\b(support\s+fedex|num[eé]ro\s+support|1-800|customer\s+service)\b",
    re.I,
)

_SOFT_THRESHOLD = 2.0


def is_tickets_workspace(message: str, *, history_text: str = "") -> bool:
    text = message or ""
    if _SHIPMENT_SUPPORT_RE.search(text):
        return False
    if is_tickets_list_utterance(text):
        return True
    if _TICKETS_MGMT_RE.search(text):
        return True
    if is_tickets_followup_message(text, history_text=history_text):
        return True
    if score_tickets_utterance(text) >= _SOFT_THRESHOLD:
        return True
    return False


def score_tickets_soft(message: str) -> float:
    return score_tickets_utterance(message)
