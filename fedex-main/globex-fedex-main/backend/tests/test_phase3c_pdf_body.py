"""Smoke tests Phase 3c — chat court + corps PDF enrichi."""

from app.services.client_phase3.pdf_body_composer import (
    compose_shipment_pdf_fallback,
    short_pdf_chat_reply,
    strip_markdown_for_pdf,
)
from app.services.simple_text_pdf_service import generate_text_pdf


def test_strip_markdown_for_pdf_removes_bold():
    assert strip_markdown_for_pdf("**Statut** : livré") == "Statut : livré"


def test_short_pdf_chat_reply_does_not_repeat_long_body():
    body = "Ligne 1\n" * 30
    reply = short_pdf_chat_reply("fr", doc_title="Suivi colis 123")
    assert "lien de téléchargement" in reply.lower()
    assert body not in reply
    assert len(reply) < 200


def test_compose_shipment_pdf_fallback_contains_tracking():
    payload = {
        "available": True,
        "tracking_number": "880892017122",
        "shipment": {
            "tracking_number": "880892017122",
            "status": "En transit",
            "current_location": "Paris",
            "estimated_delivery": "2026-06-30",
            "events": [
                {"at": "2026-06-27", "description": "En route", "location": "CDG"},
            ],
        },
    }
    text = compose_shipment_pdf_fallback(payload, "fr")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) >= 5
    assert "880892017122" in text


def test_generate_text_pdf_with_empty_lines_in_body():
    body = "Titre\n\nParagraphe après ligne vide"
    pdf_bytes, _ = generate_text_pdf(body, title="Test")
    assert pdf_bytes[:4] == b"%PDF"
