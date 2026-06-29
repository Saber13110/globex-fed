"""Tests Phase 1 — session miroir admin_client."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — enregistre tous les modèles SQLAlchemy
from app.core.database import Base
from app.models.user import User
from app.services.admin_client.session_bridge import (
    get_or_create_chat_session,
    persist_bot_message,
    persist_user_message,
    sync_history_from_request,
)
from app.services.chat_export_service import session_tracking_numbers
from app.services.chat_session_context import resolve_tracking_for_message
from app.services.client_phase3.pdf_text import last_bot_message_text


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


def test_get_or_create_reuses_session(db, admin):
    first = get_or_create_chat_session(db, admin)
    again = get_or_create_chat_session(db, admin, chat_session_id=first.id)
    assert again.id == first.id
    assert again.user_id == admin.id


def test_get_or_create_ignores_foreign_session(db, admin):
    other = User(
        email="other@test.com",
        password_hash="x",
        full_name="Other",
        role="client",
        status="active",
        organization_id="org-other-1",
    )
    db.add(other)
    db.flush()
    foreign = get_or_create_chat_session(db, other)
    mine = get_or_create_chat_session(db, admin, chat_session_id=foreign.id)
    assert mine.id != foreign.id


_BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _stamp(msg, order: int):
    """Horodatage croissant déterministe (SQLite func.now() ne distingue pas les lignes d'une même transaction)."""
    msg.created_at = _BASE_TIME + timedelta(seconds=order)
    return msg


def test_two_turns_persist_last_bot_message(db, admin):
    session = get_or_create_chat_session(db, admin)
    _stamp(persist_user_message(db, session, "Bonjour"), 0)
    _stamp(persist_bot_message(db, session, "Bonjour, comment puis-je aider ?"), 1)
    _stamp(persist_user_message(db, session, "Suivi 817950452196"), 2)
    _stamp(persist_bot_message(db, session, "Le colis 817950452196 est en transit."), 3)
    db.commit()

    assert last_bot_message_text(db, session.id) == "Le colis 817950452196 est en transit."


def test_tracking_number_recorded_in_session(db, admin):
    session = get_or_create_chat_session(db, admin)
    persist_user_message(db, session, "Suis ce colis 817950452196")
    persist_bot_message(db, session, "Le colis 817950452196 est en transit.")
    db.commit()

    assert "817950452196" in session_tracking_numbers(db, session.id, admin.id)


def test_resolve_tracking_for_followup_table_request(db, admin):
    session = get_or_create_chat_session(db, admin)
    persist_user_message(db, session, "Suis ce colis 817950452196")
    persist_bot_message(db, session, "Le colis 817950452196 est en transit.")
    db.commit()

    tn, src = resolve_tracking_for_message(
        db,
        session_id=session.id,
        user_id=admin.id,
        message="donne moi plus d'info sur ce colis dans un tableau",
    )
    assert tn == "817950452196"
    assert src == "session"


def test_sync_history_one_shot(db, admin):
    session = get_or_create_chat_session(db, admin)
    history = [
        {"role": "user", "content": "Suis le colis 817950452196"},
        {"role": "assistant", "content": "Le colis 817950452196 est en transit."},
    ]
    sync_history_from_request(db, session, history)
    for i, msg in enumerate(session.messages):
        _stamp(msg, i)
    db.flush()
    assert last_bot_message_text(db, session.id) == "Le colis 817950452196 est en transit."

    # Idempotent : un 2e appel ne duplique pas l'historique.
    sync_history_from_request(db, session, history)
    db.flush()
    tn, src = resolve_tracking_for_message(
        db,
        session_id=session.id,
        user_id=admin.id,
        message="montre la carte de ce colis",
    )
    assert tn == "817950452196"
