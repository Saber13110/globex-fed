"""Génération PDF (historique FedEx avec horodatage) pour le mode Agent client."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fpdf import FPDF


def _pdf_safe_text(value: str | None, *, max_len: int = 500) -> str:
    if not value:
        return ""
    text = str(value)[:max_len]
    for src, dst in (
        ("\u2014", "-"),
        ("\u2013", "-"),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2026", "..."),
        ("\u00a0", " "),
    ):
        text = text.replace(src, dst)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _format_event_time(raw: str | None) -> str:
    if not raw:
        return "—"
    text = str(raw).strip()
    try:
        normalized = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return text[:40]


def generate_shipment_history_pdf(data: dict[str, Any]) -> bytes:
    """PDF récapitulatif d'un colis : statut + chronologie horodatée."""
    tn = str(data.get("tracking_number") or "—")
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, _pdf_safe_text("Historique FedEx — Globex"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 6, _pdf_safe_text(f"Colis {tn}"), ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    epw = pdf.epw
    for label, val in (
        ("Statut", data.get("status")),
        ("Lieu actuel", data.get("current_location")),
        ("Livraison estimée", data.get("estimated_delivery")),
        ("Livraison effective", data.get("actual_delivery")),
        ("Destinataire", data.get("recipient")),
        ("Origine", data.get("origin_location")),
        ("Destination", data.get("destination_location")),
    ):
        if val:
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(epw, 7, _pdf_safe_text(f"{label} : {val}", max_len=300))

    events = list(data.get("events") or [])
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe_text("Chronologie des événements"), ln=True)
    pdf.set_font("Helvetica", "", 9)

    if not events:
        pdf.multi_cell(0, 6, _pdf_safe_text("Aucun événement détaillé disponible."))
    else:
        for ev in events[:40]:
            if not isinstance(ev, dict):
                continue
            when = _format_event_time(ev.get("at"))
            desc = ev.get("description") or ev.get("eventDescription") or "Mise à jour"
            loc = ev.get("location") or ""
            line = f"{when} — {desc}"
            if loc:
                line += f" ({loc})"
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(epw, 6, _pdf_safe_text(line, max_len=400))
            pdf.ln(1)

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(
        0,
        5,
        _pdf_safe_text(
            "Document généré automatiquement par l'agent FedEx Globex à partir des données FedEx."
        ),
    )
    return pdf.output()


def generate_multi_shipment_history_pdf(shipments: list[dict[str, Any]]) -> bytes:
    """PDF combiné pour plusieurs colis (session / comparaison)."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, _pdf_safe_text("Résumé expéditions FedEx — Globex"), ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, _pdf_safe_text(f"{len(shipments)} colis"), ln=True)
    pdf.ln(4)

    for idx, data in enumerate(shipments[:10]):
        if idx:
            pdf.ln(2)
        tn = str(data.get("tracking_number") or "—")
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, _pdf_safe_text(f"Colis {tn} — {data.get('status') or '—'}"), ln=True)
        pdf.set_font("Helvetica", "", 9)
        loc = data.get("current_location")
        if loc:
            pdf.cell(0, 6, _pdf_safe_text(f"Lieu : {loc}"), ln=True)
        events = list(data.get("events") or [])[:8]
        for ev in events:
            if not isinstance(ev, dict):
                continue
            when = _format_event_time(ev.get("at"))
            desc = ev.get("description") or "Mise à jour"
            loc_ev = ev.get("location") or ""
            line = f"  {when} — {desc}"
            if loc_ev:
                line += f" ({loc_ev})"
            pdf.multi_cell(0, 5, _pdf_safe_text(line, max_len=400))

    return pdf.output()


def build_tracking_status_export_download(tracking_numbers: list[str]) -> dict[str, Any]:
    """Spécification téléchargement PDF statuts FedEx (copilot admin)."""
    nums = [str(n).strip() for n in tracking_numbers if str(n).strip()][:10]
    joined = ",".join(nums)
    suffix = f"{len(nums)}-colis" if len(nums) != 1 else nums[0]
    return {
        "preset": "admin_tracking",
        "tracking_numbers": joined,
        "filename": f"tracking-status-{suffix}.pdf",
        "format": "pdf",
    }
