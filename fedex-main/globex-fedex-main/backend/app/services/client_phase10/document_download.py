"""Spécifications de téléchargement pour le catalogue documents."""

from __future__ import annotations

import re
from typing import Any

from app.services.client_phase10.document_catalog import DocumentCatalogItem

_EXCEL_HINT_RE = re.compile(r"\b(xlsx|excel|\.xlsx)\b", re.I)
_PDF_HINT_RE = re.compile(r"\b(pdf|text_pdf|\.pdf)\b", re.I)


def _format_from_source_text(source_text: str | None) -> str | None:
    blob = (source_text or "").lower()
    if _EXCEL_HINT_RE.search(blob):
        return "xlsx"
    if _PDF_HINT_RE.search(blob):
        return "pdf"
    return None


def _base_tracking_fields(item: DocumentCatalogItem) -> tuple[list[str], int]:
    tn = (item.tracking_number or "").strip()
    tracking_numbers = [tn] if tn else []
    session_id = int(item.session_id or 0)
    return tracking_numbers, session_id


def build_download_spec(item: DocumentCatalogItem) -> dict[str, Any]:
    tracking_numbers, session_id = _base_tracking_fields(item)

    if session_id:
        from app.services.client_phase7.export_session_pointer import get_session_export_pointer

        ptr = get_session_export_pointer(session_id)
        if ptr is not None:
            fmt = (ptr.fmt or "pdf").lower()
            preset = "pod" if fmt == "pod" else "tracking"
            return {
                "session_id": session_id,
                "tracking_numbers": tracking_numbers,
                "preset": preset,
                "include_events": fmt != "xlsx",
                "export_token": ptr.export_token,
                "filename": ptr.filename,
                "format": fmt if fmt in {"pdf", "xlsx"} else "pdf",
            }

    if item.doc_type == "proof":
        tn = (item.tracking_number or "").strip()
        filename = f"preuve-livraison-{tn}.pdf" if tn else "preuve-livraison.pdf"
        return {
            "session_id": session_id,
            "tracking_numbers": tracking_numbers,
            "preset": "pod",
            "include_events": True,
            "export_token": None,
            "filename": filename,
            "format": "pdf",
        }

    fmt_hint = _format_from_source_text(item.source_text)
    use_xlsx = fmt_hint == "xlsx" or (fmt_hint is None and item.doc_type == "export")

    if use_xlsx:
        tn = (item.tracking_number or "").strip()
        filename = f"export-{tn}.xlsx" if tn else "tracking-export.xlsx"
        return {
            "session_id": session_id,
            "tracking_numbers": tracking_numbers,
            "preset": "tracking",
            "include_events": False,
            "export_token": None,
            "filename": filename,
            "format": "xlsx",
        }

    tn = (item.tracking_number or "").strip()
    filename = f"rapport-{tn}.pdf" if tn else "historique-suivi.pdf"
    return {
        "session_id": session_id,
        "tracking_numbers": tracking_numbers,
        "preset": "tracking",
        "include_events": True,
        "export_token": None,
        "filename": filename,
        "format": "pdf",
    }


def download_ready_message(item: DocumentCatalogItem, *, lang: str) -> str:
    if lang == "en":
        return f'Here is your download for "{item.title}".'
    return f'Voici le téléchargement pour « {item.title} ».'
