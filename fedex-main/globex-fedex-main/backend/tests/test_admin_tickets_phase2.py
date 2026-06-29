"""Tests Phase 2 tickets — confirmation reply / resolve."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.chat_session import ChatSession
from app.models.support_ticket import SupportTicket
from app.models.user import User
from app.services.admin_client.tickets.tickets_executor import try_admin_tickets_turn


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
        email="admin-tix2@test.com",
        password_hash="x",
        full_name="Admin",
        role="admin",
        status="active",
        organization_id="org-admin-tix2",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client_user(db):
    user = User(
        email="client-tix2@test.com",
        password_hash="x",
        full_name="Client",
        role="client",
        status="active",
        organization_id="org-client-tix2",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def chat_session(db, admin):
    sess = ChatSession(user_id=admin.id, title="Test tickets p2")
    db.add(sess)
    db.flush()
    return sess


@pytest.fixture()
def open_ticket(db, client_user):
    ticket = SupportTicket(
        id=11,
        user_id=client_user.id,
        subject="Blocage douane",
        message="Mon colis est bloqué en douane depuis trois jours.",
        status="open",
        priority="medium",
    )
    db.add(ticket)
    db.commit()
    return ticket


@patch("app.services.admin_client.tickets.tickets_narrative.draft_ticket_reply")
@patch("app.services.admin_client.tickets.tickets_service.reply_to_ticket")
def test_pipeline_confirm_reply(
    mock_reply,
    mock_draft,
    db,
    admin,
    chat_session,
    open_ticket,
):
    mock_draft.return_value = "Bonjour, nous traitons votre dossier douane."
    mock_reply.return_value = {
        "ticket_id": 11,
        "subject": "Blocage douane",
        "status_after": "pending",
    }

    turn1 = try_admin_tickets_turn(
        db,
        admin,
        chat_session,
        "réponds à ce ticket",
        1,
        "fr",
        history_text="**Fiche ticket**\n#11 — SUP-11",
        conversation_history=[{"role": "assistant", "content": "**Fiche ticket**\n#11 — SUP-11"}],
    )
    assert turn1 is not None
    assert "oui ou non" in turn1["reply"].lower()
    assert turn1["intent"] == "tickets_reply"
    mock_reply.assert_not_called()

    hist = turn1["reply"]
    turn2 = try_admin_tickets_turn(
        db,
        admin,
        chat_session,
        "oui",
        2,
        "fr",
        history_text=hist,
        conversation_history=[{"role": "assistant", "content": hist}],
    )
    assert turn2 is not None
    assert turn2["intent"] == "tickets_reply_done"
    mock_reply.assert_called_once()


@patch("app.services.admin_client.tickets.tickets_service.set_ticket_status")
def test_pipeline_confirm_resolve(mock_resolve, db, admin, chat_session, open_ticket):
    mock_resolve.return_value = {
        "ticket_id": 11,
        "subject": "Blocage douane",
        "status": "resolved",
        "previous_status": "open",
    }

    turn1 = try_admin_tickets_turn(
        db,
        admin,
        chat_session,
        "marque le ticket #11 comme résolu",
        1,
        "fr",
    )
    assert turn1 is not None
    assert "oui ou non" in turn1["reply"].lower()
    assert turn1["intent"] == "tickets_resolve"

    hist = turn1["reply"]
    turn2 = try_admin_tickets_turn(
        db,
        admin,
        chat_session,
        "oui",
        2,
        "fr",
        history_text=hist,
        conversation_history=[{"role": "assistant", "content": hist}],
    )
    assert turn2 is not None
    assert turn2["intent"] == "tickets_resolve_done"
    mock_resolve.assert_called_once()
