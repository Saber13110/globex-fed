"""Scénario e2e liste → détail utilisateurs (mocks)."""

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


@patch("app.services.admin_client.users.users_tool.get_user_detail")
@patch("app.services.admin_client.users.users_tool.list_users")
def test_e2e_list_then_detail(mock_list, mock_detail, db, admin, chat_session):
    now = datetime.now(timezone.utc)
    mock_list.return_value = [
        {
            "id": 3,
            "full_name": "Bob",
            "email": "bob@test.com",
            "role": "client",
            "status": "active",
            "created_at": now,
        }
    ]
    mock_detail.return_value = {
        "id": 3,
        "full_name": "Bob",
        "email": "bob@test.com",
        "role": "client",
        "status": "active",
        "messages_count": 5,
        "trackings_count": 2,
        "organization_id": "org-1",
        "is_online": False,
    }

    list_turn = try_admin_users_turn(db, admin, chat_session, "liste les utilisateurs", 1, "fr")
    assert list_turn is not None
    hist = list_turn["reply"]

    detail_turn = try_admin_users_turn(
        db,
        admin,
        chat_session,
        "détail du #3",
        2,
        "fr",
        history_text=hist,
    )
    assert detail_turn is not None
    assert detail_turn["intent"] == "users_detail"
    assert "bob@test.com" in detail_turn["reply"]
    mock_detail.assert_called()
