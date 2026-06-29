"""Tests pipeline tickets admin — mocks."""

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
        email="admin@test.com",
        password_hash="x",
        full_name="Admin",
        role="admin",
        status="active",
        organization_id="org-admin-tickets",
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


@patch("app.services.admin_client.tickets.tickets_tool.list_tickets")
def test_pipeline_list_metadata(mock_list, db, admin, chat_session):
    now = datetime.now(timezone.utc)
    mock_list.return_value = [
        {
            "id": 1,
            "ticket_number": "TKT-001",
            "subject": "Colis bloqué",
            "status": "open",
            "priority": "high",
            "user_email": "client@test.com",
            "created_at": now,
        }
    ]
    out = try_admin_tickets_turn(db, admin, chat_session, "liste les tickets ouverts", 1, "fr")
    assert out is not None
    assert out["tool_called"] is True
    assert out["data_source"] == "admin_support_api"
    assert out["intent"] == "tickets_list"
    assert "Colis bloqué" in out["reply"]
    assert "client@test.com" in out["reply"]
