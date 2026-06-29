"""Allowlist intent métier — priorité sur détection attaque."""

from __future__ import annotations

import re

from app.services.client_phase11.ticket_intent import is_support_workspace
from app.services.client_phase5.notification_filters import is_notification_workspace
from app.services.client_phase6.watch_intent import is_watch_workspace
from app.services.client_phase8.daily_report_intent import is_daily_report_workspace
from app.services.llm.tracking_extract import extract_tracking_number
from app.utils.tracking_parser import is_plausible_tracking_number

_CONV_RE = re.compile(r"\b(conversations?|discussions?|chats?)\b", re.I)
_SESSION_LIST_RE = re.compile(
    r"\b(liste|lister|montre|montrez|affiche|affichez|voir|donne|donnez|"
    r"resume|resumer|r[eé]sum[eé]|summarize|recent|recentes?)\b",
    re.I,
)
_DOC_WORKSPACE_RE = re.compile(
    r"\b("
    r"documents?|fichiers?|exports?|preuves?|rapports?|"
    r"mes fichiers|mes documents|page documents|biblioth[eè]que|"
    r"t[eé]l[eé]charge|download"
    r")\b",
    re.I,
)
_GREETING_RE = re.compile(
    r"^(bonjour|bonsoir|salut|hello|hi|coucou|merci|thanks|thank you|ok|bye|au revoir)\b",
    re.I,
)
_TRACKING_VERB_RE = re.compile(
    r"\b(suiv(?:re|i|s|ez)|track(?:ing)?|colis|num[eé]ro de suivi|tracking|exp[eé]dition|"
    r"where is|o[uù] est|statut|localisation|shipment)\b",
    re.I,
)
_TRACKING_ONLY_RE = re.compile(r"^\s*\d{12,14}\s*$")


def detect_business_intent(message: str) -> str | None:
    text = (message or "").strip()
    if not text:
        return None
    if _GREETING_RE.search(text):
        return "greeting"
    if is_daily_report_workspace(text):
        return "daily_report"
    try:
        from app.services.admin_client.dashboard.dashboard_workspace import is_dashboard_workspace

        if is_dashboard_workspace(text):
            return "admin_dashboard"
    except ImportError:
        pass
    try:
        from app.services.admin_client.reports.reports_workspace import is_reports_workspace

        if is_reports_workspace(text):
            return "admin_reports"
    except ImportError:
        pass
    if is_support_workspace(text):
        return "support"
    if _DOC_WORKSPACE_RE.search(text):
        return "documents"
    if _CONV_RE.search(text) and _SESSION_LIST_RE.search(text):
        return "sessions"
    if is_notification_workspace(text):
        return "notifications"
    if is_watch_workspace(text):
        return "watch"
    tn = extract_tracking_number(text)
    if tn and is_plausible_tracking_number(tn):
        if _TRACKING_VERB_RE.search(text) or _TRACKING_ONLY_RE.match(text):
            return "tracking"
    if _TRACKING_VERB_RE.search(text):
        return "tracking"
    return None
