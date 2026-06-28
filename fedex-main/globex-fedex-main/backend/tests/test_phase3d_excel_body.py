"""Smoke tests Phase 3d — chat court + Excel enrichi."""

from app.services.chat_export_service import generate_shipment_excel_from_fedex
from app.services.client_phase3.excel_body_composer import (
    compose_excel_layout_fallback,
    short_excel_chat_reply,
)


def test_short_excel_chat_reply_is_brief():
    body = "Statut\n" * 30
    reply = short_excel_chat_reply("fr", doc_title="Suivi colis 123")
    assert "lien de téléchargement" in reply.lower()
    assert body not in reply
    assert len(reply) < 200


def test_compose_excel_layout_fallback_with_events():
    payload = {
        "available": True,
        "shipment": {
            "tracking_number": "880892017122",
            "events": [{"at": "2026-06-27", "description": "En route"}],
        },
    }
    assert compose_excel_layout_fallback(payload) == "summary_and_events"


def test_generate_shipment_excel_from_fedex_produces_xlsx():
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
    xlsx_bytes, filename = generate_shipment_excel_from_fedex(
        payload,
        layout="summary_and_events",
        lang="fr",
    )
    assert xlsx_bytes[:2] == b"PK"
    assert filename.endswith(".xlsx")
    assert "880892017122" in filename or "suivi" in filename
