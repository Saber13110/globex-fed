"""Tests handler admin « 1 » / « 2 » après clarification PDF."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.services.admin_client.pdf_clarify_followup import (
    is_pdf_clarify_choice_message,
    is_pdf_clarify_pending,
    try_admin_pdf_clarify_choice_turn,
)
from app.services.admin_client.pipeline import run_admin_client_turn
from app.services.admin_client.session_bridge import (
    get_or_create_chat_session,
    persist_bot_message,
    persist_user_message,
)
from app.services.globex_agent import kernel as kernel_mod

TN_A = "817581472369"
TN_B = "817725683025"

CLARIFY_FR = (
    "Je vois plusieurs réponses récentes. Souhaitez-vous :\n"
    f"1. Un PDF de ma dernière réponse sur le colis **{TN_B}**\n"
    "2. Un PDF résumé de toute notre conversation ?\n\n"
    "Répondez par 1 ou 2, ou reformulez votre demande."
)


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


def _seed_two_shipments_and_clarify(db, admin):
    session = get_or_create_chat_session(db, admin)
    persist_user_message(db, session, f"suivi colis {TN_A}")
    persist_bot_message(
        db, session, f"Le colis {TN_A} est en transit vers Paris.", source="fedex_api"
    )
    persist_user_message(db, session, f"suivi colis {TN_B}")
    persist_bot_message(
        db, session, f"Le colis {TN_B} est livré à Lyon.", source="fedex_api"
    )
    persist_user_message(db, session, "genere ces infos en pdf")
    persist_bot_message(db, session, CLARIFY_FR, source="phase3")
    db.commit()
    return session


def test_is_pdf_clarify_choice_message():
    assert is_pdf_clarify_choice_message("1") is True
    assert is_pdf_clarify_choice_message("2") is True
    assert is_pdf_clarify_choice_message("option 1") is True
    assert is_pdf_clarify_choice_message("12") is False
    assert is_pdf_clarify_choice_message("bonjour") is False


def test_is_pdf_clarify_pending():
    assert is_pdf_clarify_pending(last_bot_text=CLARIFY_FR) is True
    assert is_pdf_clarify_pending(last_bot_text="Colis en transit.") is False
    assert is_pdf_clarify_pending(
        conversation_history=[{"role": "assistant", "content": CLARIFY_FR}]
    ) is True


@patch("app.services.admin_client.pdf_clarify_followup.build_text_pdf_download")
def test_clarify_then_1_exports_pdf(mock_build, db, admin):
    session = _seed_two_shipments_and_clarify(db, admin)
    mock_build.return_value = {
        "preset": "text_pdf",
        "filename": f"suivi-{TN_B}.pdf",
        "format": "pdf",
        "export_token": "tokchoice1",
        "session_id": session.id,
    }

    result = run_admin_client_turn(
        db,
        admin,
        "1",
        ui_language="fr",
        chat_session_id=session.id,
        conversation_history=[
            {"role": "assistant", "content": CLARIFY_FR},
        ],
    )

    assert result is not None
    assert result["intent"] == "export_pdf"
    assert result["export_download"]["export_token"] == "tokchoice1"
    assert TN_B in (result.get("tracking_number") or TN_B)
    mock_build.assert_called_once()
    body = mock_build.call_args[0][1]
    assert TN_B in body or "Lyon" in body


@patch("app.services.admin_client.pdf_clarify_followup.handle_conversation_pdf_turn")
def test_clarify_then_2_conversation_pdf(mock_conv, db, admin):
    session = _seed_two_shipments_and_clarify(db, admin)
    mock_conv.return_value = {
        "reply": "Voici le résumé PDF.",
        "source": "export",
        "intent": "export_pdf",
        "tracking_number": None,
        "llm_provider": "ollama",
        "shipment": None,
        "export_download": {"export_token": "tokconv2", "format": "pdf"},
    }

    result = run_admin_client_turn(
        db,
        admin,
        "2",
        ui_language="fr",
        chat_session_id=session.id,
        conversation_history=[{"role": "assistant", "content": CLARIFY_FR}],
    )

    assert result is not None
    assert result["export_download"]["export_token"] == "tokconv2"
    mock_conv.assert_called_once()
    assert "résumé" in mock_conv.call_args[0][3].lower() or "summary" in mock_conv.call_args[0][3].lower()


def test_bare_1_without_clarify_not_engaged(db, admin):
    assert run_admin_client_turn(db, admin, "1", ui_language="fr") is None


@patch("app.services.globex_agent.kernel.admin_ollama_chat")
@patch("app.services.globex_agent.kernel.try_admin_simple_actions")
def test_clarify_choice_skips_ollama(mock_bridge, mock_ollama, db, admin):
    session = _seed_two_shipments_and_clarify(db, admin)
    settings = MagicMock()
    settings.globex_simple_mode = True

    with patch("app.services.globex_agent.kernel.get_settings", return_value=settings):
        with patch(
            "app.services.admin_client.pdf_clarify_followup.build_text_pdf_download",
            return_value={
                "preset": "text_pdf",
                "filename": "x.pdf",
                "format": "pdf",
                "export_token": "tokkernel1",
                "session_id": session.id,
            },
        ):
            result = kernel_mod.run_globex_agent_chat(
                db,
                admin,
                "1",
                ui_language="fr",
                agent_mode=True,
                chat_session_id=session.id,
                conversation_history=[{"role": "assistant", "content": CLARIFY_FR}],
            )

    mock_ollama.assert_not_called()
    mock_bridge.assert_not_called()
    assert result is not None
    assert result.get("export_download") is not None


def test_try_admin_pdf_clarify_returns_none_without_marker(db, admin):
    session = get_or_create_chat_session(db, admin)
    persist_bot_message(db, session, "Réponse simple sans clarify.")
    db.commit()
    assert (
        try_admin_pdf_clarify_choice_turn(
            db, admin, session, "1", user_msg_id=99, ui_language="fr"
        )
        is None
    )
