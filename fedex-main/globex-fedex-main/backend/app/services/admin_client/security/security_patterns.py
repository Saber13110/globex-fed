"""Patterns partagés Security IDS — workspace et intent."""

from __future__ import annotations

import re
import unicodedata

SECURITY_LIST_UTTERANCE_RE = re.compile(
    r"\b("
    r"liste.{0,40}(incident[s]?|ids|alertes?\s+s[eé]curit[eé]?)|"
    r"list.{0,40}(incident[s]?|security)|"
    r"donne.{0,35}(incident[s]?|ids)|"
    r"montre.{0,35}(incident[s]?|ids)|"
    r"affiche.{0,35}(incident[s]?|ids)|"
    r"incident[s]?\s+(ouverts?|open|r[eé]solus?|resolved|ferm[eé]s?|false\s+positif|faux\s+positif)"
    r")\b",
    re.I,
)

SCAN_RE = re.compile(
    r"\b("
    r"lance.{0,25}(scan|ids)|"
    r"scanne.{0,25}(s[eé]curit[eé]?|ids|incident)|"
    r"d[eé]clench.{0,20}(scan|ids)|"
    r"run.{0,15}(ids|security)\s+scan|"
    r"analyse.{0,20}ids"
    r")\b",
    re.I,
)

SUMMARY_RE = re.compile(
    r"\b("
    r"(r[eé]sum[eé]|resume|summary|synth[eè]se).{0,50}"
    r"(incident[s]?\s+ouverts?|incidents?\s+ouvert|incidents?\s+open|ids|s[eé]curit[eé]?)"
    r"|resume.{0,30}incident[s]?\s+ouverts?"
    r")\b",
    re.I,
)

REPORT_RE = re.compile(
    r"\b("
    r"rapport.{0,45}(s[eé]curit[eé]?|ids|incident)|"
    r"security\s+report|rapport\s+ids|"
    r"donne.{0,35}rapport.{0,25}(s[eé]curit[eé]?|ids)"
    r")\b",
    re.I,
)

DETAIL_RE = re.compile(
    r"\b(fiche|d[eé]tail|infos?|voir|consulte|ouvr|ouvert).{0,35}(incident|ids|alerte)\b",
    re.I,
)

INCIDENT_CATALOG_RE = re.compile(
    r"\b(incident[s]?\s+s[eé]curit[eé]?|security\s+incident|ids|intrusion|menace|faux\s+positif)\b",
    re.I,
)

# Anomalies dans les journaux → agent Logs, pas Security IDS
LOGS_ANOMALY_SCOPE_RE = re.compile(
    r"\b(anomal|suspect).{0,30}(logs?|journaux?|journal)\b|"
    r"\b(logs?|journaux?).{0,30}(anomal|suspect)\b",
    re.I,
)


def normalize_security_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def is_security_report_message(message: str) -> bool:
    norm = normalize_security_text(message)
    return bool(REPORT_RE.search(norm))


def message_targets_incidents(message: str) -> bool:
    """True si l'utilisateur parle explicitement d'incidents IDS (pas tickets/logs)."""
    text = message or ""
    if re.search(r"\b(incident[s]?|ids|menace|faux\s+positif)\b", text, re.I):
        return True
    if re.search(r"\bids\b", text, re.I) and re.search(
        r"\b(scan|s[eé]curit|alerte|ouvert|r[eé]solu)\b", text, re.I
    ):
        return True
    return False


def is_logs_anomaly_scope(message: str) -> bool:
    """Délègue les anomalies de journaux à l'agent Logs."""
    return bool(LOGS_ANOMALY_SCOPE_RE.search(normalize_security_text(message)))


def is_security_list_utterance(message: str) -> bool:
    if is_logs_anomaly_scope(message):
        return False
    return bool(SECURITY_LIST_UTTERANCE_RE.search(normalize_security_text(message)))


def score_security_utterance(message: str) -> float:
    if is_logs_anomaly_scope(message):
        return 0.0
    norm = normalize_security_text(message)
    if SCAN_RE.search(norm):
        return 3.0
    if is_security_list_utterance(message):
        return 3.0
    if SUMMARY_RE.search(norm):
        return 3.0
    if REPORT_RE.search(norm):
        return 3.0
    if DETAIL_RE.search(norm):
        return 3.0
    if re.search(r"\bincident\s*#\s*\d+", norm, re.I):
        return 3.0
    if re.search(r"\bresume.{0,30}incident", norm, re.I):
        return 3.0
    if INCIDENT_CATALOG_RE.search(norm):
        return 2.0
    return 0.0
