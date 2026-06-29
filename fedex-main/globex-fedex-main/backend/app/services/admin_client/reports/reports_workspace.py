"""Espace de travail centre de rapports admin — gate Jarvis."""

from __future__ import annotations

import re
import unicodedata

from app.services.admin_client.reports.reports_followup import is_reports_followup_message

_REPORTS_CENTER_RE = re.compile(
    r"\b("
    r"centre\s+de\s+rapports?|reports?\s+center|"
    r"rapports?\s+(export[eé]s?|g[eé]n[eé]r[eé]s?|admin|globex)|"
    r"exports?\s+r[eé]cents?|recent\s+exports?|"
    r"pr[eé]v[ei]s?ualis|prev[ei]s?ualis|preview|aper[cç]u|"
    r"re[- ]?t[eé]l[eé]charg|t[eé]l[eé]charge|telecharg|redownload|ret[eé]l[eé]charg|"
    r"partage[rz]?\s+(le\s+)?rapport|share\s+(the\s+)?report|"
    r"envo(?:ie|ye|yer)\s+(le\s+)?rapport|send\s+(the\s+)?report|"
    r"dernier\s+(export|reports?|rapports?)|last\s+(export|reports?)|"
    r"tracking[- ]history|delivery[- ]performance|financial[- ]summary|"
    r"liste.{0,30}(rapports?|reports?|exports?)|"
    r"list.{0,30}(rapports?|reports?|exports?)|"
    r"(tous les|all)\s+(les\s+)?(rapports?|reports?|exports?)|"
    r"liste\s+(des\s+)?rapports?|list\s+reports?|"
    r"montre.{0,20}(rapports?|reports?|exports?)"
    r")\b",
    re.I,
)

_DASHBOARD_DELAY_REPORT_RE = re.compile(
    r"\brapport\s+(des\s+)?retards?|delay\s+report\b",
    re.I,
)

_SIGNAL_PATTERNS: dict[str, list[tuple[re.Pattern[str], float]]] = {
    "list": [
        (re.compile(r"\b(liste|list|montre|affiche|donne).{0,30}(reports?|rapports?|exports?)\b", re.I), 3.0),
        (re.compile(r"\b(tous les|all)\s+(les\s+)?(reports?|rapports?|exports?)\b", re.I), 3.0),
        (re.compile(r"\b(exports?\s+r[eé]cents?|recent\s+exports?|historique\s+exports?)\b", re.I), 2.5),
    ],
    "preview": [
        (re.compile(r"\b(pr[eé]v[ei]s?ualis|prev[ei]s?ualis|preview|aper[cç]u)\b", re.I), 3.0),
        (re.compile(r"\b(voir|montre).{0,20}contenu\b", re.I), 2.0),
    ],
    "download": [
        (re.compile(r"\b(re[- ]?t[eé]l[eé]charg|t[eé]l[eé]charge|telecharg|redownload|download)\b", re.I), 3.0),
        (re.compile(r"\bt[eé]l[eé]charge[rz]?\s+(le\s+)?(dernier\s+)?export\b", re.I), 2.5),
    ],
    "share": [
        (re.compile(r"\b(partage[rz]?|share)\b", re.I), 2.5),
        (
            re.compile(
                r"\b(envo(?:ie|ye|yer)|send)\s+.{0,25}(rapport|report|export)\b",
                re.I,
            ),
            2.5,
        ),
        (
            re.compile(
                r"\b(envo(?:ie|ye|yer)|send)\s+.{0,20}(mail|e-mail|email)\s+.{0,40}(rapport|report)\b",
                re.I,
            ),
            2.5,
        ),
    ],
    "catalog": [
        (re.compile(r"\b(centre\s+de\s+rapports?|reports?\s+center)\b", re.I), 3.0),
        (re.compile(r"^\s*reports?\s*$", re.I), 2.5),
        (re.compile(r"\b(reports?|rapports?|exports?)\b", re.I), 1.5),
    ],
}

_SOFT_THRESHOLD = 2.0
_GREY_ZONE = 1.0


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").strip())
    return "".join(c for c in folded if not unicodedata.combining(c))


def normalize_reports_text(message: str) -> str:
    return _normalize(message).lower()


def score_reports_soft(message: str) -> float:
    """Score agrégé — entrée workspace si >= seuil."""
    text = normalize_reports_text(message)
    if not text:
        return 0.0
    total = 0.0
    for patterns in _SIGNAL_PATTERNS.values():
        for pat, weight in patterns:
            if pat.search(text):
                total += weight
    return total


def is_reports_grey_zone(message: str) -> bool:
    text = normalize_reports_text(message)
    dim_scores: dict[str, float] = {k: 0.0 for k in _SIGNAL_PATTERNS}
    for dim, patterns in _SIGNAL_PATTERNS.items():
        for pat, weight in patterns:
            if pat.search(text):
                dim_scores[dim] += weight
    ranked = sorted(dim_scores.items(), key=lambda x: x[1], reverse=True)
    if not ranked or ranked[0][1] < _GREY_ZONE:
        return False
    top_score = ranked[0][1]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_score < _SOFT_THRESHOLD:
        return True
    return top_score - second_score < _GREY_ZONE


def is_reports_workspace(message: str, *, history_text: str = "") -> bool:
    """Vrai si le tour relève du centre de rapports admin (ReportRun)."""
    text = _normalize(message)
    if not text:
        return False
    if _DASHBOARD_DELAY_REPORT_RE.search(text):
        return False
    if is_reports_followup_message(text, history_text=history_text):
        return True
    if _REPORTS_CENTER_RE.search(text):
        return True
    return score_reports_soft(text) >= _SOFT_THRESHOLD
