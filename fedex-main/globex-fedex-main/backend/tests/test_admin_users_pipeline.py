"""Tests pipeline utilisateurs admin."""

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
from app.models.user import User
from app.services.admin_client.users.users_executor import try_admin_users_turn


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


@pytest.fixture()
def chat_session(db, admin):
    sess = ChatSession(user_id=admin.id, title="Test")
    db.add(sess)
    db.flush()
    return sess


@patch("app.services.admin_client.users.users_tool.list_users")
def test_pipeline_list_metadata(mock_list, db, admin, chat_session):
    now = datetime.now(timezone.utc)
    mock_list.return_value = [
        {
            "id": 1,
            "full_name": "Bob",
            "email": "bob@test.com",
            "role": "client",
            "status": "active",
            "created_at": now,
        }
    ]
    out = try_admin_users_turn(db, admin, chat_session, "liste les utilisateurs", 1, "fr")
    assert out is not None
    assert out["tool_called"] is True
    assert out["data_source"] == "admin_users_api"
    assert out["raw_data_received"] is True
    assert "bob@test.com" in out["reply"]
    assert "Bob" in out["reply"] or "bob@test.com" in out["reply"]


@patch("app.services.admin_client.users.users_tool.get_user_detail")
@patch("app.services.admin_client.users.users_service.suspend_user_account")
def test_pipeline_confirm_suspend(mock_suspend, mock_detail, db, admin, chat_session):
    mock_detail.return_value = {
        "id": 2,
        "full_name": "Alice",
        "email": "alice@test.com",
        "role": "client",
        "status": "active",
    }
    turn1 = try_admin_users_turn(db, admin, chat_session, "suspend le compte #2", 1, "fr")
    assert turn1 is not None
    assert "oui ou non" in turn1["reply"].lower() or "Répondez" in turn1["reply"]

    mock_suspend.return_value = {"suspended": True, "user_id": 2, "email": "alice@test.com"}
    hist = turn1["reply"]
    turn2 = try_admin_users_turn(
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
    assert turn2["intent"] == "users_suspend_done"
    mock_suspend.assert_called_once()
