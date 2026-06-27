"""PDF texte libre — contenu personnalisé (hors export DB)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fpdf import FPDF


def _pdf_safe(text: str | None, *, max_len: int = 4000) -> str:
    if not text:
        return ""
    s = str(text).replace("\r", " ").strip()[:max_len]
    for a, b in (("—", "-"), ("'", "'"), ("'", "'"), ("«", '"'), ("»", '"')):
        s = s.replace(a, b)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _slug_filename(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (text or "document")[:40]).strip("-").lower()
    return slug or "document"


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
        pdf.multi_cell(0, 6, _pdf_safe(line, max_len=500))

    return pdf.output(), filename
