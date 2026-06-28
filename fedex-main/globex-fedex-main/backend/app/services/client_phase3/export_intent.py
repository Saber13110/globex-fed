"""Détection intent export PDF / Excel — Phase 3a (partiellement DISABLED).

wants_pdf_format et la classification fine sont dans pdf_postprocess.py.
classify_pdf_kind conservé pour référence legacy uniquement.
"""

from __future__ import annotations

import re
from enum import Enum

from app.services.chat_export_service import is_export_intent

_PDF_KEYWORDS = re.compile(
    r"\b(pdf|rapport|document|fichier|t[eé]l[eé]charger|exporter|export)\b",
    re.I,
)

_SUMMARY_KEYWORDS = re.compile(
    r"\b(r[eé]sum[eé]|synth[eè]se|recap|r[eé]capitulatif|conversation|discussion|historique\s+chat)\b",
    re.I,
)

_WRAP_REPLY_KEYWORDS = re.compile(
    r"\b("
    r"ta\s+r[eé]ponse|ton\s+r[eé]ponse|ce\s+que\s+tu\s+viens\s+de\s+dire|"
    r"derni[eè]re\s+r[eé]ponse|mets\s+[çc]a|met\s+[çc]a|"
    r"ce\s+message|ce\s+texte"
    r")\b",
    re.I,
)

_TRACKING_KEYWORDS = re.compile(
    r"\b("
    r"colis|suivi|tracking|historique|livraison|exp[eé]dition|"
    r"num[eé]ro\s+de\s+suivi|shipments?"
    r")\b",
    re.I,
)

_TRACKING_SUMMARY_PRESET = re.compile(
    r"\b(aujourd'?hui|du\s+jour|r[eé]sum[eé]\s+du\s+jour|daily)\b",
    re.I,
)

_EXCEL_KEYWORDS = re.compile(r"\b(excel|xlsx|tableur)\b", re.I)
_EXPLICIT_EXCEL = re.compile(r"\b(excel|xlsx|tableur)\b", re.I)
_EXPLICIT_PDF = re.compile(r"\bpdf\b", re.I)


def has_explicit_excel_format(message: str) -> bool:
    return bool(_EXPLICIT_EXCEL.search(message or ""))


def has_explicit_pdf_format(message: str) -> bool:
    return bool(_EXPLICIT_PDF.search(message or ""))


class PdfKind(str, Enum):
    tracking = "tracking"
    text_summary = "text_summary"
    wrap_reply = "wrap_reply"
    free_text = "free_text"


def is_pdf_export_intent(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if has_explicit_excel_format(text) and not has_explicit_pdf_format(text):
        return False
    if "pdf" in text.lower():
        return True
    if _PDF_KEYWORDS.search(text):
        return True
    if _SUMMARY_KEYWORDS.search(text) and re.search(
        r"\b(pdf|fichier|document|t[eé]l[eé]charger|exporter)\b", text, re.I
    ):
        return True
    return False


def is_excel_export_intent(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if has_explicit_pdf_format(text) and not has_explicit_excel_format(text):
        return False
    text_lower = text.lower()
    if _EXCEL_KEYWORDS.search(text):
        return True
    return is_export_intent(message) and ("excel" in text_lower or "xlsx" in text_lower)


def is_client_export_request(message: str) -> bool:
    return is_pdf_export_intent(message) or is_excel_export_intent(message)


def classify_pdf_kind(
    message: str,
    *,
    has_session_trackings: bool = False,
    has_last_bot_reply: bool = False,
) -> PdfKind:
    """
    DISABLED Phase 3a — ne plus utiliser pour router le chat client.
    Remplacé par pdf_postprocess (LLM d'abord, PDF ensuite).
    """
    text = (message or "").strip()
    if _WRAP_REPLY_KEYWORDS.search(text):
        return PdfKind.wrap_reply
    if _SUMMARY_KEYWORDS.search(text) and not _TRACKING_KEYWORDS.search(text):
        return PdfKind.text_summary
    # Bug Phase 3a : forçait tracking dès qu'un numéro était en session — ne pas réactiver tel quel
    if _TRACKING_KEYWORDS.search(text) or has_session_trackings:
        return PdfKind.tracking
    if has_last_bot_reply and re.search(r"\b(pdf|fichier|document)\b", text, re.I):
        return PdfKind.wrap_reply
    if _PDF_KEYWORDS.search(text) or "pdf" in text.lower():
        return PdfKind.text_summary
    return PdfKind.free_text


def tracking_pdf_preset(message: str) -> str:
    if _TRACKING_SUMMARY_PRESET.search(message or ""):
        return "tracking_summary"
    if re.search(r"\bhistorique\b", message or "", re.I):
        return "tracking"
    return "tracking_summary"
