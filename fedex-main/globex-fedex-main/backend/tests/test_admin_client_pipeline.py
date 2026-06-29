"""Tests pipeline admin_client — orchestration suivi / PDF / Excel.

Le pipeline réutilise les modules client (déjà testés). On vérifie ici l'orchestration :
gating, résolution du numéro de suivi en relance, propagation de `export_download`,
`shipment`, persistance de la réponse et `chat_session_id`.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — enregistre tous les modèles SQLAlchemy
from app.core.database import Base
from app.models.user import User
from app.services.admin_client import pipeline as pipeline_mod
from app.services.admin_client.pipeline import run_admin_client_turn
from app.services.admin_client.session_bridge import persist_bot_message, persist_user_message


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def admin(db):
    user = User(
        email="admin@test.com",
        password_hash="x",
        full_name="Admin",
        role="admin",
        status="active",
        organization_id="org-admin-1",
    )
    db.add(user)
    db.flush()
    return user


def _fedex_payload(tracking_number: str = "817950452196", *, status: str = "In transit") -> dict:
    return {
        "available": True,
        "tracking_number": tracking_number,
        "shipment": {
            "tracking_number": tracking_number,
            "status": status,
            "current_location": "Paris",
            "estimated_delivery": "2026-06-30",
            "events": [
                {
                    "at": "2026-06-27T10:00:00",
                    "description": "Arrived at facility",
                    "location": "Paris",
                    "latitude": 48.8566,
                    "longitude": 2.3522,
                },
                {
                    "at": "2026-06-26T08:00:00",
                    "description": "Departed origin",
                    "location": "Lyon",
                    "latitude": 45.764,
                    "longitude": 4.8357,
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------


def test_greeting_is_not_engaged(db, admin):
    assert run_admin_client_turn(db, admin, "bonjour", ui_language="fr") is None


def test_general_admin_question_not_engaged(db, admin):
    assert run_admin_client_turn(db, admin, "combien d'utilisateurs actifs ?", ui_language="fr") is None


# ---------------------------------------------------------------------------
# Suivi (intents structurés, sans LLM)
# ---------------------------------------------------------------------------


@patch("app.services.chatbot_service.fetch_fedex_tracking_data")
def test_tracking_tabular_history(mock_fetch, db, admin):
    mock_fetch.return_value = _fedex_payload()
    result = run_admin_client_turn(
        db, admin, "donne le suivi du colis 817950452196 dans un tableau", ui_language="fr"
    )
    assert result is not None
    assert "817950452196" in result["reply"]
    assert result["intent"] == "tabular_history"
    assert result["chat_session_id"] is not None
    mock_fetch.assert_called_once_with("817950452196")


@patch("app.services.chatbot_service.fetch_fedex_tracking_data")
def test_tracking_map_request_returns_shipment_card(mock_fetch, db, admin):
    mock_fetch.return_value = _fedex_payload()
    result = run_admin_client_turn(
        db, admin, "montre la carte du colis 817950452196", ui_language="fr"
    )
    assert result is not None
    assert result["intent"] == "map_tracking"
    assert result["shipment"] is not None
    assert result["shipment"]["show_tracking_map"] is True


@patch("app.services.chatbot_service.fetch_fedex_tracking_data")
def test_tracking_followup_resolves_tn_from_session(mock_fetch, db, admin):
    """Relance « dans un tableau » sans numéro : résolution depuis l'historique de session."""
    mock_fetch.return_value = _fedex_payload()
    first = run_admin_client_turn(
        db, admin, "montre la carte du colis 817950452196", ui_language="fr"
    )
    assert first is not None
    chat_session_id = first["chat_session_id"]

    mock_fetch.reset_mock()
    second = run_admin_client_turn(
        db,
        admin,
        "donne plus d'info sur ce colis dans un tableau",
        ui_language="fr",
        chat_session_id=chat_session_id,
    )
    assert second is not None
    assert second["intent"] == "tabular_history"
    assert "817950452196" in second["reply"]
    mock_fetch.assert_called_once_with("817950452196")


# ---------------------------------------------------------------------------
# PDF / Excel (orchestration post-réponse, internes client mockés)
# ---------------------------------------------------------------------------


@patch("app.services.admin_client.pipeline.handle_conversation_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_admin_free_text_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_admin_shipment_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.handle_excel_only_followup_turn", return_value=None)
@patch("app.services.admin_client.pipeline.maybe_attach_pdf_export")
@patch("app.services.chatbot_service.fetch_fedex_tracking_data")
def test_tracking_with_pdf_export_propagates_download(
    mock_fetch, mock_pdf, _excel_early, _shipment, _free_text, _conv_pdf, db, admin
):
    mock_fetch.return_value = _fedex_payload()
    pdf_dl = {"filename": "suivi-817950452196.pdf", "format": "pdf", "export_token": "tok123"}
    mock_pdf.return_value = ("Voici votre PDF de suivi.", pdf_dl, "export_pdf")

    result = run_admin_client_turn(
        db, admin, "donne le suivi du colis 817950452196 dans un tableau en pdf", ui_language="fr"
    )
    assert result is not None
    assert result["export_download"] == pdf_dl
    assert result["intent"] == "export_pdf"
    assert result["action_executed"] is True
    mock_pdf.assert_called_once()


@patch("app.services.admin_client.pipeline.handle_conversation_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_admin_free_text_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_admin_shipment_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.handle_excel_only_followup_turn", return_value=None)
@patch("app.services.admin_client.pipeline.maybe_attach_excel_export")
@patch("app.services.chatbot_service.fetch_fedex_tracking_data")
def test_tracking_with_excel_export_propagates_download(
    mock_fetch, mock_excel, _excel_early, _shipment, _free_text, _conv_pdf, db, admin
):
    mock_fetch.return_value = _fedex_payload()
    xlsx_dl = {"filename": "suivi-817950452196.xlsx", "format": "xlsx", "export_token": "tok456"}
    mock_excel.return_value = ("Voici votre fichier Excel.", xlsx_dl, "export_excel")

    result = run_admin_client_turn(
        db, admin, "donne le suivi du colis 817950452196 dans un tableau en excel", ui_language="fr"
    )
    assert result is not None
    assert result["export_download"] == xlsx_dl
    assert result["intent"] == "export_excel"
    mock_excel.assert_called_once()


@patch("app.services.admin_client.pipeline.handle_conversation_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.handle_excel_only_followup_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_admin_free_text_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_admin_shipment_pdf_turn")
def test_pdf_only_followup_engages_export_handler(mock_shipment, _free_text, _excel_early, _conv_pdf, db, admin):
    """Relance « mets en pdf » sur la dernière réponse : routée vers le routeur PDF admin."""
    from app.services.admin_client.session_bridge import get_or_create_chat_session

    session = get_or_create_chat_session(db, admin)
    persist_user_message(db, session, "suivi 817950452196")
    persist_bot_message(db, session, "Le colis 817950452196 est en transit.")
    db.commit()

    pdf_dl = {"filename": "reponse.pdf", "format": "pdf", "export_token": "tok789"}
    mock_shipment.return_value = {
        "reply": "Voici le PDF.",
        "source": "export",
        "intent": "export_pdf",
        "tracking_number": "817950452196",
        "llm_provider": "ollama",
        "shipment": None,
        "export_download": pdf_dl,
    }

    result = run_admin_client_turn(
        db, admin, "mets le en pdf", ui_language="fr", chat_session_id=session.id
    )
    assert result is not None
    assert result["export_download"] == pdf_dl
    assert result["intent"] == "export_pdf"
    mock_shipment.assert_called_once()


# ---------------------------------------------------------------------------
# Documents (Phase 9) — lecture image / PDF
# ---------------------------------------------------------------------------


@patch("app.services.admin_client.pipeline.try_document_read_turn")
def test_document_upload_routes_to_document_handler(mock_doc, db, admin):
    mock_doc.return_value = {
        "reply": "La facture indique un total de 100 EUR.",
        "source": "agent_document",
        "intent": "document_read",
        "tracking_number": None,
        "llm_provider": "gemini",
        "shipment": None,
        "export_download": None,
    }
    result = run_admin_client_turn(
        db,
        admin,
        "résume ce document",
        ui_language="fr",
        image_base64="Zm9v",
        image_mime_type="application/pdf",
        file_name="facture.pdf",
    )
    assert result is not None
    assert result["intent"] == "document_read"
    assert "100 EUR" in result["reply"]
    assert result["chat_session_id"] is not None
    mock_doc.assert_called_once()


@patch("app.services.admin_client.pipeline.try_admin_shipment_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_admin_free_text_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.handle_conversation_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.handle_excel_only_followup_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_document_followup_turn")
def test_document_followup_question_routes_to_followup_handler(
    mock_followup, mock_excel, mock_conv_pdf, mock_free_text, mock_shipment, db, admin
):
    mock_followup.return_value = {
        "reply": "Le document mentionne la date du 12 juin.",
        "source": "agent_document",
        "intent": "document_followup",
        "tracking_number": None,
        "llm_provider": "gemini",
        "shipment": None,
        "export_download": None,
    }
    result = run_admin_client_turn(
        db, admin, "et quelle est la date sur le document ?", ui_language="fr"
    )
    assert result is not None
    assert result["intent"] == "document_followup"
    mock_followup.assert_called_once()


@patch("app.services.chatbot_service._compute_phase2_reply")
def test_tracking_wins_over_document_followup_with_pdf_in_session(mock_phase2, db, admin):
    """Suivi explicite avec PDF en session : pas de document followup."""
    from app.services.admin_client.session_bridge import get_or_create_chat_session

    mock_phase2.return_value = (
        "Colis en transit.",
        "fedex",
        "tracking_status",
        "817950452196",
        "fedex_api",
        {"tracking_number": "817950452196", "status": "in_transit"},
    )
    session = get_or_create_chat_session(db, admin)
    persist_user_message(
        db,
        session,
        "résume ce document",
        image_base64="Zm9v",
        image_mime_type="application/pdf",
        file_name="facture.pdf",
    )
    persist_bot_message(db, session, "Facture de 100 EUR.")
    db.commit()

    result = run_admin_client_turn(
        db,
        admin,
        "donne le suivi du colis 817950452196",
        ui_language="fr",
        chat_session_id=session.id,
    )
    assert result is not None
    assert result["intent"] == "tracking_status"
    assert result["intent"] != "document_followup"


# ---------------------------------------------------------------------------
# Notifications (Phase 5 sur PlatformNotification)
# ---------------------------------------------------------------------------


@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_notifications_list_platform_fallback(mock_sync, _ollama, db, admin):
    from app.models.platform_notification import PlatformNotification
    from datetime import datetime, timezone

    del mock_sync
    db.add(
        PlatformNotification(
            external_key="pipe-test-1",
            category="colis",
            title="Shipment Delay Alert",
            message="Tracking #123 is delayed",
            tracking_number="123",
            priority="high",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    result = run_admin_client_turn(db, admin, "montre mes notifications", ui_language="fr")
    assert result is not None
    assert result["intent"] == "notifications_query"
    assert "Shipment Delay Alert" in result["reply"]


@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_notifications_filter_unread(mock_sync, _ollama, db, admin):
    del mock_sync
    result = run_admin_client_turn(
        db, admin, "mes notifications non lues", ui_language="fr"
    )
    assert result is not None
    assert result["intent"] == "notifications_query"
    assert "Aucune notification" in result["reply"] or "notification" in result["reply"].lower()


@patch("app.services.notifications_service.mark_all_read", return_value=3)
@patch("app.services.client_phase5.router._call_ollama_notifications_plan")
def test_notifications_mark_all_read(mock_ollama, mock_mark, db, admin):
    mock_ollama.return_value = {
        "task_type": "notifications_mark_all_read",
        "assistant_intro": "",
        "answers": {},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    result = run_admin_client_turn(
        db, admin, "marque toutes mes notifications comme lues", ui_language="fr"
    )
    assert result is not None
    assert result["intent"] == "notifications_mark_all_read"
    assert "3" in result["reply"]
    mock_mark.assert_called_once()
