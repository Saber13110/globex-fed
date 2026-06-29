"""Régression flux admin utilisateur — suivi FedEx + PDF colis/followup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.services.admin_client.admin_pdf_router import is_admin_shipment_pdf_request
from app.services.admin_client.pdf_free_text import is_free_text_pdf_request
from app.services.admin_client.pipeline import run_admin_client_turn
from app.services.admin_client.session_bridge import (
    get_or_create_chat_session,
    persist_bot_message,
    persist_user_message,
)
from app.services.globex_agent import kernel as kernel_mod

TRACKING = "817725683025"


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


def _fedex_payload(tracking_number: str = TRACKING) -> dict:
    return {
        "available": True,
        "tracking_number": tracking_number,
        "shipment": {
            "tracking_number": tracking_number,
            "status": "In transit",
            "current_location": "Paris",
            "estimated_delivery": "2026-06-30",
            "events": [],
        },
    }


def test_greeting_returns_none_for_kernel_ollama(db, admin):
    assert run_admin_client_turn(db, admin, "salut", ui_language="fr") is None


@patch("app.services.chatbot_service.fetch_fedex_tracking_data")
def test_tracking_live_not_ollama(mock_fetch, db, admin):
    mock_fetch.return_value = _fedex_payload()
    result = run_admin_client_turn(
        db,
        admin,
        f"tu peux me suivre ce colis {TRACKING}",
        ui_language="fr",
    )
    assert result is not None
    assert TRACKING in result["reply"]
    assert result.get("intent") in ("tracking_status", "summary", "status", "shipment_status")
    tools = result.get("tools_used") or []
    assert any("admin_client" in t for t in tools)
    assert not any("ollama_chat" in t for t in tools)
    mock_fetch.assert_called_once_with(TRACKING)


@patch("app.services.admin_client.admin_pdf_router.handle_pdf_only_followup_turn")
@patch("app.services.chatbot_service.fetch_fedex_tracking_data")
def test_genrer_sous_forme_pdf_uses_followup_not_free_text(
    mock_fetch, mock_followup, db, admin
):
    mock_fetch.return_value = _fedex_payload()
    first = run_admin_client_turn(
        db,
        admin,
        f"tu peux me suivre ce colis {TRACKING}",
        ui_language="fr",
    )
    assert first is not None
    session_id = first["chat_session_id"]

    pdf_dl = {"filename": "suivi.pdf", "format": "pdf", "export_token": "tokfollow1"}
    mock_followup.return_value = {
        "reply": "Voici le PDF.",
        "source": "export",
        "intent": "export_pdf",
        "tracking_number": TRACKING,
        "llm_provider": None,
        "shipment": None,
        "export_download": pdf_dl,
    }

    with patch(
        "app.services.admin_client.pipeline.try_admin_free_text_pdf_turn"
    ) as mock_free:
        result = run_admin_client_turn(
            db,
            admin,
            "tu peux me genrer sous form de fichier pdf",
            ui_language="fr",
            chat_session_id=session_id,
        )

    assert result is not None
    assert result["intent"] == "export_pdf"
    assert result["export_download"] == pdf_dl
    mock_followup.assert_called()
    mock_free.assert_not_called()


@patch("app.services.admin_client.admin_pdf_router.run_tracking_pdf_export")
@patch("app.services.chatbot_service.fetch_fedex_tracking_data")
def test_colis_pdf_uses_run_tracking_pdf_export(mock_fetch, mock_run_export, db, admin):
    mock_fetch.return_value = _fedex_payload()
    first = run_admin_client_turn(
        db,
        admin,
        f"tu peux me suivre ce colis {TRACKING}",
        ui_language="fr",
    )
    session_id = first["chat_session_id"]

    pdf_dl = {"filename": f"suivi-{TRACKING}.pdf", "format": "pdf", "export_token": "tokcolis"}
    mock_run_export.return_value = ("", pdf_dl, TRACKING)

    result = run_admin_client_turn(
        db,
        admin,
        "tu peux me genrer les infos de ce colis sous form de fichier pdf",
        ui_language="fr",
        chat_session_id=session_id,
    )

    assert result is not None
    assert result["intent"] == "export_pdf"
    assert result["export_download"] == pdf_dl
    mock_run_export.assert_called_once()


@patch("app.services.admin_client.admin_pdf_router.run_tracking_pdf_export")
@patch("app.services.chatbot_service.fetch_fedex_tracking_data")
def test_ces_infos_pdf_not_free_text(mock_fetch, mock_run_export, db, admin):
    mock_fetch.return_value = _fedex_payload()
    first = run_admin_client_turn(
        db,
        admin,
        f"tu peux me suivre ce colis {TRACKING}",
        ui_language="fr",
    )
    session_id = first["chat_session_id"]

    pdf_dl = {"filename": "suivi.pdf", "format": "pdf", "export_token": "tokces"}
    mock_run_export.return_value = ("", pdf_dl, TRACKING)

    msg = "je veux que tu me genere ces infos sous forme de fichier pdf"
    assert is_free_text_pdf_request(msg, has_session_tracking=True) is False
    assert is_admin_shipment_pdf_request(msg, has_session_tracking=True) is True

    with patch(
        "app.services.admin_client.pipeline.try_admin_free_text_pdf_turn"
    ) as mock_free:
        mock_free.return_value = {
            "reply": "wrong",
            "source": "export",
            "intent": "export_pdf",
            "export_download": {"export_token": "wrong"},
        }
        result = run_admin_client_turn(
            db,
            admin,
            msg,
            ui_language="fr",
            chat_session_id=session_id,
        )

    assert result is not None
    assert result["export_download"]["export_token"] == "tokces"
    mock_run_export.assert_called_once()


@patch("app.services.globex_agent.kernel.admin_ollama_chat")
@patch("app.services.globex_agent.kernel.run_admin_client_turn", return_value=None)
@patch("app.services.globex_agent.kernel.try_admin_simple_actions", return_value=None)
@patch("app.services.globex_agent.kernel.try_admin_kernel_tracking_rescue", return_value=None)
def test_kernel_no_ollama_hallucination_on_tracking(
    _rescue, _bridge, _pipeline, mock_ollama, db, admin
):
    settings = MagicMock()
    settings.globex_simple_mode = True
    with patch("app.services.globex_agent.kernel.get_settings", return_value=settings):
        result = kernel_mod.run_globex_agent_chat(
            db,
            admin,
            f"suivre le colis {TRACKING}",
            ui_language="fr",
            agent_mode=True,
        )

    mock_ollama.assert_not_called()
    assert result is not None
    assert result.get("llm_degraded") is True
    assert "FedEx" in result["reply"] or "interroger" in result["reply"]


@patch("app.services.globex_agent.admin_action_bridge.plan_export_tools")
def test_bridge_skips_export_tracking_pdf_for_shipment(mock_plan, db, admin):
    mock_plan.return_value = [("export_tracking_pdf", {"tracking_number": TRACKING})]
    from app.services.globex_agent.admin_action_bridge import try_admin_simple_actions

    result = try_admin_simple_actions(
        db,
        admin,
        "tu peux me genrer les infos de ce colis sous form de fichier pdf",
        conversation_history=[
            {"role": "user", "content": f"suivi {TRACKING}"},
            {"role": "assistant", "content": f"Colis {TRACKING} en transit."},
        ],
        ui_language="fr",
        agent_mode=True,
    )
    assert result is None
    mock_plan.assert_called_once()
