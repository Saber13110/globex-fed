"""Tests confirmation utilisateurs via session DB."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.chat_message import ChatMessage, MessageSender
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.admin_client.pipeline import run_admin_client_turn
from app.services.admin_client.users.users_pending import build_users_pending_marker


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


def test_oui_confirms_via_chat_session_db(db, admin):
    sess = ChatSession(user_id=admin.id, title="Users")
    db.add(sess)
    db.flush()
    marker = build_users_pending_marker("suspend", 5, {})
    bot_text = "Confirmez?" + marker
    db.add(
        ChatMessage(
            session_id=sess.id,
            sender=MessageSender.bot.value,
            message_text=bot_text,
        )
    )
    db.commit()

    with patch("app.services.admin_client.users.users_service.suspend_user_account") as mock_suspend:
        mock_suspend.return_value = {"suspended": True, "user_id": 5, "email": "a@test.com"}
        with patch("app.services.admin_client.users.users_tool.get_user_detail") as mock_detail:
            mock_detail.return_value = {
                "id": 5,
                "email": "a@test.com",
                "full_name": "A",
                "role": "client",
                "status": "active",
            }
            out = run_admin_client_turn(
                db,
                admin,
                "oui",
                ui_language="fr",
                chat_session_id=sess.id,
                conversation_history=[],
            )
    assert out is not None
    assert out.get("intent") == "users_suspend_done"
    mock_suspend.assert_called_once()


def test_oui_reactivate_wins_over_stale_email_pending(db, admin):
    """Un vieux brouillon e-mail ne doit pas voler le oui d'une réactivation."""
    from app.services.admin_client.email.email_pending import build_email_pending_marker
    from app.services.admin_client.pending_confirm import try_admin_pending_confirm_turn

    sess = ChatSession(user_id=admin.id, title="Users vs email")
    db.add(sess)
    db.flush()

    stale_email = (
        "Brouillon e-mail"
        + build_email_pending_marker(
            to="amine@gmail.com",
            subject="Information concernant votre compte Globex FedEx",
            body_text="Bonjour, votre compte est suspendu.",
            user_id=5,
        )
    )
    db.add(
        ChatMessage(
            session_id=sess.id,
            sender=MessageSender.bot.value,
            message_text=stale_email,
        )
    )
    db.flush()

    users_marker = build_users_pending_marker("reactivate", 5, {})
    reactivate_confirm = "Confirmation requise" + users_marker
    db.add(
        ChatMessage(
            session_id=sess.id,
            sender=MessageSender.bot.value,
            message_text=reactivate_confirm,
        )
    )
    db.commit()

    with patch("app.services.admin_client.users.users_service.reactivate_user_account") as mock_reactivate:
        mock_reactivate.return_value = {
            "reactivated": True,
            "user_id": 5,
            "email": "amine@gmail.com",
        }
        with patch("app.services.admin_client.users.users_tool.get_user_detail") as mock_detail:
            mock_detail.return_value = {
                "id": 5,
                "email": "amine@gmail.com",
                "full_name": "amine",
                "role": "client",
                "status": "active",
            }
            with patch("app.services.admin_client.email.email_service.send_email") as mock_send:
                out = try_admin_pending_confirm_turn(
                    db,
                    admin,
                    sess,
                    "oui",
                    "fr",
                    conversation_history=[{"role": "assistant", "content": reactivate_confirm}],
                )

    assert out is not None
    assert out.get("intent") == "users_reactivate_done"
    mock_reactivate.assert_called_once()
    mock_send.assert_not_called()
