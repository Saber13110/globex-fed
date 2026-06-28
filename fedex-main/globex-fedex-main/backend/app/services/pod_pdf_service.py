"""Génération PDF de preuve de livraison à partir des métadonnées disponibles."""

from __future__ import annotations

from typing import Any

from fpdf import FPDF


def _safe_text(value: Any, max_len: int = 200) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    return text[:max_len]


def generate_pod_pdf(pod_info: dict[str, Any]) -> bytes:
    """Construit un PDF POD lisible (FedEx ou données dérivées du tracking)."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "FedEx Proof of Delivery", ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, "Globex FedEx Chatbot — document genere a partir des donnees FedEx", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    rows = [
        ("Numero de suivi", pod_info.get("tracking_number")),
        ("Statut", pod_info.get("status")),
        ("Date de livraison", pod_info.get("delivered_at")),
        ("Heure de livraison", pod_info.get("delivered_time") or pod_info.get("delivered_at")),
        ("Adresse de livraison", pod_info.get("delivery_address")),
        ("Destinataire / recu par", pod_info.get("received_by_name")),
        ("Service transporteur", pod_info.get("carrier_service")),
        ("Localisation actuelle", pod_info.get("current_location")),
        ("Signature disponible", "Oui" if pod_info.get("signature_available") else "Non"),
        ("Source", pod_info.get("source") or "fedex_tracking"),
    ]

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 10, "Details de livraison", ln=True)
    pdf.set_font("Helvetica", "", 10)

    label_w = 62
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(label_w, 8, _safe_text(label, 40) + " :", border=0)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 8, _safe_text(value, 300))
        pdf.ln(1)

    if pod_info.get("delivery_notes"):
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Notes FedEx", ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 7, _safe_text(pod_info.get("delivery_notes"), 800))

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(
        0,
        5,
        "Ce document est genere automatiquement lorsque FedEx ne fournit pas de PDF SPOD. "
        "Les informations proviennent de l'API Tracking / Advanced Integrated Visibility.",
    )

    out = pdf.output()
    if isinstance(out, bytearray):
        return bytes(out)
    if isinstance(out, bytes):
        return out
    return out.encode("latin-1", errors="replace")
