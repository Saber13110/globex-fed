"""Détection intention export par e-mail — Phase 7."""

from __future__ import annotations

import re
import unicodedata

_EMAIL_RE = re.compile(r"\b(mail|email|courriel|e-mail)\b", re.I)
_SEND_RE = re.compile(r"\b(envoie|envoyer|envoyez|forward|transmet)\b", re.I)
_EXPORT_DOC_RE = re.compile(
    r"\b(pdf|excel|xlsx|export|document|fichier|rapport|pi[eè]ce jointe|attachment)\b",
    re.I,
)
_EMAIL_ONLY_FOLLOWUP_RE = re.compile(
    r"\b("
    r"envoie(-|\s)?(le|moi|la|les)?|"
    r"par mail|par email|par courriel|"
    r"re[cç]ois par mail|forward"
    r")\b",
    re.I,
)
_WATCH_EXCLUDE_RE = re.compile(
    r"(surveill\w*|previens?\w*|pr[eé]ven\w*|alerte colis|tiens-moi au courant|watch shipment)",
    re.I,
)
_DAILY_REPORT_EXCLUDE_RE = re.compile(
    r"(rapport du jour|rapport quotidien|rapport d activite|rapport d'activite|"
    r"bilan du jour|bilan activite|recap du jour|récap du jour|daily report|"
    r"activite aujourd|activité aujourd|mon activite|mon activité|journal du jour)",
    re.I,
)


def normalize_message_text(message: str) -> str:
    text = unicodedata.normalize("NFKD", (message or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def _is_pdf_export_message(message: str) -> bool:
    from app.services.client_phase3.export_intent import is_pdf_export_intent

    return is_pdf_export_intent(message)


def _is_excel_export_message(message: str) -> bool:
    from app.services.client_phase3.export_intent import is_excel_export_intent

    return is_excel_export_intent(message)


def is_export_email_only_followup(message: str) -> bool:
    text = normalize_message_text(message)
    if not text:
        return False
    if not (_EMAIL_RE.search(text) or _SEND_RE.search(text)):
        return False
    if _is_pdf_export_message(message) or _is_excel_export_message(message):
        return False
    if _WATCH_EXCLUDE_RE.search(text):
        return False
    if _DAILY_REPORT_EXCLUDE_RE.search(text):
        return False
    if _EMAIL_ONLY_FOLLOWUP_RE.search(text):
        return True
    if _SEND_RE.search(text) and _EMAIL_RE.search(text):
        return True
    return False


def wants_export_by_email(message: str) -> bool:
    text = normalize_message_text(message)
    if not text:
        return False
    if _DAILY_REPORT_EXCLUDE_RE.search(text):
        return False
    if is_export_email_only_followup(message):
        return True
    if not _EMAIL_RE.search(text) and not (_SEND_RE.search(text) and _EXPORT_DOC_RE.search(text)):
        return False
    if _is_pdf_export_message(message) or _is_excel_export_message(message):
        return True
    if _EXPORT_DOC_RE.search(text) and (_EMAIL_RE.search(text) or _SEND_RE.search(text)):
        return True
    return False
