"""PDF texte libre — contenu personnalisé (hors export DB)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fpdf import FPDF
from fpdf.errors import FPDFException


def _pdf_safe(text: str | None, *, max_len: int = 4000) -> str:
    if not text:
        return ""
    s = str(text).replace("\r", " ").strip()[:max_len]
    for src, dst in (
        ("\u2014", "-"),
        ("\u2013", "-"),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2026", "..."),
        ("\u00a0", " "),
        ("—", "-"),
        ("'", "'"),
        ("'", "'"),
        ("«", '"'),
        ("»", '"'),
    ):
        s = s.replace(src, dst)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _slug_filename(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "document")[:40]).strip("-").lower()
    return slug or "document"


def _write_pdf_line(pdf: FPDF, line: str, *, line_height: float = 6) -> None:
    """Écrit une ligne dans le PDF ; découpe les tokens trop longs si besoin."""
    safe = _pdf_safe(line, max_len=500)
    if not safe.strip():
        pdf.ln(line_height)
        return
    width = pdf.epw
    pdf.set_x(pdf.l_margin)
    try:
        pdf.multi_cell(width, line_height, safe)
    except FPDFException:
        chunk_size = 80
        for i in range(0, len(safe), chunk_size):
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(width, line_height, safe[i : i + chunk_size])


def generate_text_pdf(
    text: str,
    *,
    title: str | None = None,
) -> tuple[bytes, str]:
    """Génère un PDF minimal avec le texte fourni."""
    body = (text or "").strip()
    if not body:
        raise ValueError("Texte vide — impossible de générer le PDF.")

    heading = (title or body[:80]).strip()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"text-{_slug_filename(body)}-{ts}.pdf"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _pdf_safe(heading), ln=True)
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 11)
    for line in body.splitlines() or [body]:
        _write_pdf_line(pdf, line)

    return pdf.output(), filename
