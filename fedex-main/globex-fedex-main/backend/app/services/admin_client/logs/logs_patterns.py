"""Patterns partagés logs — workspace et intent utilisent les mêmes signaux."""

from __future__ import annotations

import re
import unicodedata

LOGS_LIST_UTTERANCE_RE = re.compile(
    r"\b("
    r"liste.{0,45}(logs?|journaux?|activit[eé])|"
    r"list.{0,45}(logs?|activity)|"
    r"donne.{0,45}(logs?|journaux?)|"
    r"montre.{0,45}(logs?|journaux?)|"
    r"affiche.{0,45}(logs?|journaux?)|"
    r"journaux?\s+d.?activit[eé]|activity\s+logs?|"
    r"filtrer.{0,30}(logs?|journaux?)"
    r")\b",
    re.I,
)

# Logs ciblés sur UN utilisateur → agent Users, pas Logs global
USER_SCOPED_LOGS_RE = re.compile(
    r"\b(logs?|journaux?|historique\s+d.?activit[eé]).{0,35}"
    r"(?:utilisateur|user|compte|"
    r"de\s+l['']?(?:utilisateur|user|compte)|"
    r"du\s+(?:utilisateur|user|compte)|"
    r"pour\s+(?:l['']?)?(?:utilisateur|user|compte))",
    re.I,
)

LOGS_CATALOG_RE = re.compile(r"\b(logs?|journaux?|journal\s+d.?audit)\b", re.I)

ANOMALY_RE = re.compile(
    r"\b(anomal|anomalies?|suspect|intrusion|alerte\s+s[eé]curit|security\s+log|logs?\s+suspects?)\b",
    re.I,
)

CONVERSATION_FROM_LOG_RE = re.compile(
    r"\b("
    r"ouvr(?:e|ir)|ouvert|affiche|montre|voir|consulte|acc[eè]de"
    r").{0,40}(conversation|fil|discussion|chat|session)",
    re.I,
)

OPEN_LOG_RE = re.compile(
    r"\b(ouvr(?:e|ir)|ouvert|voir|consulte|montre|affiche).{0,30}(log|journal)\b",
    re.I,
)

SUSPEND_FROM_LOG_RE = re.compile(
    r"\b(suspend|bloqu|ban).{0,50}(log|journal|depuis\s+ce|de\s+ce)\b|"
    r"\b(suspend|bloqu).{0,30}(utilisateur|user|compte).{0,30}(log|journal)\b",
    re.I,
)


def normalize_logs_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def is_user_scoped_logs_message(message: str) -> bool:
    """True si la demande concerne les logs d'un utilisateur précis (→ agent Users)."""
    text = normalize_logs_text(message)
    if USER_SCOPED_LOGS_RE.search(text):
        return True
    if re.search(r"\blogs?\s+(de\s+)?[\w.+-]+@[\w.-]+\.\w+", text, re.I):
        return True
    if re.search(r"\buser\s+logs?\b", text, re.I):
        return True
    return False


def is_logs_list_utterance(message: str) -> bool:
    if is_user_scoped_logs_message(message):
        return False
    return bool(LOGS_LIST_UTTERANCE_RE.search(normalize_logs_text(message)))


def score_logs_utterance(message: str) -> float:
    if is_user_scoped_logs_message(message):
        return 0.0
    norm = normalize_logs_text(message)
    if is_logs_list_utterance(message):
        return 3.0
    if ANOMALY_RE.search(norm):
        return 3.0
    if CONVERSATION_FROM_LOG_RE.search(norm):
        return 3.0
    if re.search(r"\b(r[eé]sum[eé]|summary).{0,40}(activit[eé]?|logs?|journaux?)\b", norm, re.I):
        return 3.0
    if re.search(r"\b(fiche|d[eé]tail|infos?|ouvr|ouvert).{0,35}(log|journal)\b", norm, re.I):
        return 3.0
    if re.search(r"\blog\s*#\s*\d+", norm, re.I):
        return 3.0
    if SUSPEND_FROM_LOG_RE.search(norm):
        return 3.0
    if re.search(r"\bcherche.{0,30}(logs?|journaux?)\b", norm, re.I):
        return 2.5
    if re.search(
        r"\b(excel|xlsx|pdf).{0,45}(logs?|journaux?)|(logs?|journaux?).{0,45}(excel|xlsx|pdf)\b",
        norm,
        re.I,
    ):
        return 3.0
    if LOGS_CATALOG_RE.search(norm):
        return 1.5
    return 0.0
