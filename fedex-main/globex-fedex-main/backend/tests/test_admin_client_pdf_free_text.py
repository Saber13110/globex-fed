"""Tests PDF texte libre admin — détection, literal, intégration pipeline."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.services.admin_client.pdf_free_text import (
    extract_literal_pdf_body,
    is_free_text_pdf_request,
    try_admin_free_text_pdf_turn,
)
from app.services.admin_client.pipeline import run_admin_client_turn
from app.services.admin_client.session_bridge import (
    get_or_create_chat_session,
    persist_bot_message,
    persist_user_message,
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


def test_is_free_text_pdf_request_generative_contient():
    assert is_free_text_pdf_request("genere un pdf qui contient bonjour") is True
    assert is_free_text_pdf_request("je veux que tu me genere un pdf qui contient bonjour") is True


def test_is_free_text_pdf_request_shipment_colis_not_free_text():
    msg = "tu peux me genrer les infos de ce colis sous form de fichier pdf"
    assert is_free_text_pdf_request(msg, has_session_tracking=True) is False
    assert is_free_text_pdf_request("genrer sous form de fichier pdf") is False


def test_is_free_text_pdf_request_pure_followup():
    assert is_free_text_pdf_request("mets en pdf") is False
    assert is_free_text_pdf_request("exporte en pdf") is False


def test_extract_literal_pdf_body_contient():
    assert extract_literal_pdf_body("genere un pdf qui contient bonjour") == "bonjour"
    assert extract_literal_pdf_body('fais un pdf avec le texte « hello world »') == "hello world"


def test_extract_literal_pdf_body_genere_dans_pdf():
    assert extract_literal_pdf_body("je veux que tu me genere salut dans un pdf") == "salut"
    assert extract_literal_pdf_body("mets hello en pdf") == "hello"


@patch("app.services.admin_client.pdf_free_text.build_text_pdf_download")
def test_try_admin_free_text_salut_with_prior_tracking_session(mock_build, db, admin):
    """Literal salut même si la session contient déjà un suivi colis."""
    session = get_or_create_chat_session(db, admin)
    persist_user_message(db, session, "suis le colis 880849626649")
    persist_bot_message(db, session, "Le colis 880849626649 est en transit.")
    db.commit()
    mock_build.return_value = {
        "preset": "text_pdf",
        "filename": "salut.pdf",
        "format": "pdf",
        "export_token": "toksalut01",
        "session_id": session.id,
    }

    result = try_admin_free_text_pdf_turn(
        db,
        admin,
        session,
        "je veux que tu me genere salut dans un pdf",
        user_msg_id=99,
        ui_language="fr",
    )

    assert result is not None
    assert result["intent"] == "export_pdf"
    assert mock_build.call_args[0][1] == "salut"
    assert "Suivi colis" not in (result.get("reply") or "")


@patch("app.services.admin_client.pdf_free_text.draft_pdf_content", return_value="Contenu libre.")
@patch("app.services.admin_client.pdf_free_text.build_text_pdf_download")
def test_admin_llm_pdf_without_session_history(mock_build, mock_draft, db, admin):
    session = get_or_create_chat_session(db, admin)
    persist_bot_message(db, session, "Le colis 880849626649 est en transit.")
    db.commit()
    mock_build.return_value = {
        "preset": "text_pdf",
        "filename": "doc.pdf",
        "format": "pdf",
        "export_token": "tokllm01",
        "session_id": session.id,
    }

    result = try_admin_free_text_pdf_turn(
        db,
        admin,
        session,
        "fais un pdf qui explique les avantages du suivi FedEx pour un client",
        user_msg_id=1,
        ui_language="fr",
    )

    assert result is not None
    assert result["export_download"]["export_token"] == "tokllm01"
    mock_draft.assert_called_once()
    assert mock_draft.call_args.kwargs.get("conversation_history") is None


@patch("app.services.admin_client.pdf_free_text.build_text_pdf_download")
def test_run_admin_client_turn_salut_dans_pdf(mock_build, db, admin):
    mock_build.return_value = {
        "preset": "text_pdf",
        "filename": "salut.pdf",
        "format": "pdf",
        "export_token": "toksalut02",
        "session_id": 1,
    }

    result = run_admin_client_turn(
        db,
        admin,
        "je veux que tu me genere salut dans un pdf",
        ui_language="fr",
    )

    assert result is not None
    assert result["intent"] == "export_pdf"
    assert mock_build.call_args[0][1] == "salut"
    assert "Je n'ai pas encore de réponse" not in result["reply"]


@patch("app.services.admin_client.pdf_free_text.build_text_pdf_download")
def test_try_admin_free_text_pdf_turn_literal(mock_build, db, admin):
    session = get_or_create_chat_session(db, admin)
    db.flush()
    mock_build.return_value = {
        "preset": "text_pdf",
        "filename": "doc.pdf",
        "format": "pdf",
        "export_token": "tok12345678",
        "session_id": session.id,
    }

    result = try_admin_free_text_pdf_turn(
        db,
        admin,
        session,
        "je veux que tu me genere un pdf qui contient bonjour",
        user_msg_id=1,
        ui_language="fr",
    )

    assert result is not None
    assert result["intent"] == "export_pdf"
    assert result["export_download"]["export_token"] == "tok12345678"
    mock_build.assert_called_once()
    assert mock_build.call_args[0][1] == "bonjour"


@patch("app.services.admin_client.pipeline.try_admin_free_text_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_admin_shipment_pdf_turn")
@patch("app.services.admin_client.pipeline.handle_conversation_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.handle_excel_only_followup_turn", return_value=None)
def test_mets_en_pdf_uses_followup_not_free_text(
    _excel, _conv, mock_shipment_pdf, _free_text, db, admin
):
    session = get_or_create_chat_session(db, admin)
    persist_user_message(db, session, "suivi 817950452196")
    persist_bot_message(db, session, "Le colis 817950452196 est en transit.")
    db.commit()

    pdf_dl = {"filename": "reponse.pdf", "format": "pdf", "export_token": "tok789"}
    mock_shipment_pdf.return_value = {
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
    mock_shipment_pdf.assert_called_once()
    _free_text.assert_not_called()


@patch("app.services.admin_client.pdf_free_text.build_text_pdf_download")
def test_run_admin_client_turn_literal_bonjour_without_prior_bot(mock_build, db, admin):
    mock_build.return_value = {
        "preset": "text_pdf",
        "filename": "bonjour.pdf",
        "format": "pdf",
        "export_token": "tokliteral1",
        "session_id": 1,
    }

    result = run_admin_client_turn(
        db,
        admin,
        "je veux que tu me genere un pdf qui contient bonjour",
        ui_language="fr",
    )

    assert result is not None
    assert result["intent"] == "export_pdf"
    assert result["export_download"]["export_token"] == "tokliteral1"
    assert mock_build.call_args[0][1] == "bonjour"
    assert "Je n'ai pas encore de réponse" not in result["reply"]


@patch("app.services.admin_client.pipeline.try_admin_free_text_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.try_admin_shipment_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.handle_conversation_pdf_turn", return_value=None)
@patch("app.services.admin_client.pipeline.handle_excel_only_followup_turn", return_value=None)
def test_shipment_pdf_runs_before_free_text(
    _excel, _conv, mock_shipment, mock_free_text, db, admin
):
    session = get_or_create_chat_session(db, admin)
    persist_user_message(db, session, "suivi 817950452196")
    persist_bot_message(db, session, "Le colis est en transit.")
    db.commit()
    mock_shipment.return_value = {
        "reply": "PDF ok",
        "source": "export",
        "intent": "export_pdf",
        "tracking_number": None,
        "llm_provider": None,
        "shipment": None,
        "export_download": {"export_token": "x"},
    }

    run_admin_client_turn(db, admin, "mets en pdf", chat_session_id=session.id)

    mock_shipment.assert_called_once()
    mock_free_text.assert_not_called()
