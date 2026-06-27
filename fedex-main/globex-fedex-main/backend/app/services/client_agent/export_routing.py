# =============================================================================
# LEGACY DESACTIVE — refonte client_agent v2 (Phase 0)
# Ne pas réactiver sans retirer le bloc ACTIVE ci-dessous.
# =============================================================================
# """Routage intent export PDF — assistant client."""
#
# from __future__ import annotations
#
# import re
# from enum import Enum
#
# from app.utils.pdf_text_extract import extract_custom_pdf_text
#
# _PDF_KEYWORDS = re.compile(
#     r"\b(pdf|rapport|document|fichier|t[eé]l[eé]charger|exporter|export)\b",
#     re.I,
# )
#
# _SUMMARY_KEYWORDS = re.compile(
#     r"\b(r[eé]sum[eé]|synth[eè]se|recap|r[eé]capitulatif|conversation|discussion|historique\s+chat)\b",
#     re.I,
# )
#
# _WRAP_REPLY_KEYWORDS = re.compile(
#     r"\b("
#     r"ta\s+r[eé]ponse|ton\s+r[eé]ponse|ce\s+que\s+tu\s+viens\s+de\s+dire|"
#     r"derni[eè]re\s+r[eé]ponse|mets\s+[çc]a|met\s+[çc]a|"
#     r"ce\s+message|ce\s+texte"
#     r")\b",
#     re.I,
# )
#
# _TRACKING_KEYWORDS = re.compile(
#     r"\b("
#     r"colis|suivi|tracking|historique|livraison|exp[eé]dition|"
#     r"num[eé]ro\s+de\s+suivi|shipments?"
#     r")\b",
#     re.I,
# )
#
# _TRACKING_SUMMARY_PRESET = re.compile(
#     r"\b(aujourd'?hui|du\s+jour|r[eé]sum[eé]\s+du\s+jour|daily)\b",
#     re.I,
# )
#
#
# class PdfKind(str, Enum):
#     tracking = "tracking"
#     summary = "summary"
#     free_text = "free_text"
#     wrap_reply = "wrap_reply"
#     composed = "composed"
#
#
# def is_pdf_export_intent(message: str) -> bool:
#     """True si le message demande explicitement un PDF ou un export fichier."""
#     text = (message or "").strip()
#     if not text:
#         return False
#     if _PDF_KEYWORDS.search(text):
#         return True
#     if _SUMMARY_KEYWORDS.search(text) and re.search(
#         r"\b(pdf|fichier|document|t[eé]l[eé]charger|exporter)\b", text, re.I
#     ):
#         return True
#     return False
#
#
# def classify_pdf_kind(
#     message: str,
#     *,
#     has_session_trackings: bool = False,
#     has_last_bot_reply: bool = False,
# ) -> PdfKind:
#     """Classifie le type de contenu PDF demandé."""
#     text = (message or "").strip()
#     if extract_custom_pdf_text(text):
#         return PdfKind.free_text
#     if _WRAP_REPLY_KEYWORDS.search(text):
#         return PdfKind.wrap_reply
#     if _SUMMARY_KEYWORDS.search(text) and not _TRACKING_KEYWORDS.search(text):
#         return PdfKind.summary
#     if _TRACKING_KEYWORDS.search(text) or has_session_trackings:
#         if _SUMMARY_KEYWORDS.search(text) and not _TRACKING_KEYWORDS.search(text):
#             return PdfKind.summary
#         return PdfKind.tracking
#     if has_last_bot_reply and re.search(r"\b(pdf|fichier|document)\b", text, re.I):
#         return PdfKind.wrap_reply
#     return PdfKind.composed
#
#
# def tracking_pdf_preset(message: str) -> str:
#     """preset tracking_summary ou tracking selon le message."""
#     if _TRACKING_SUMMARY_PRESET.search(message or ""):
#         return "tracking_summary"
#     if re.search(r"\bhistorique\b", message or "", re.I):
#         return "tracking"
#     return "tracking"
# =============================================================================
# ACTIVE — Phase 0 stub
# =============================================================================
"""client_agent — stub Phase 0."""
