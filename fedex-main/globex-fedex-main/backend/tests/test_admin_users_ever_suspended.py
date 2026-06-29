"""Tests liste historique suspensions (ActivityLog)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.activity_log import ActivityLog
from app.models.user import User
from app.services.admin_client.users.users_service import list_users_ever_suspended


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


def test_list_users_ever_suspended_from_logs(db):
    u1 = User(
        email="once@test.com",
        password_hash="x",
        full_name="Once",
        role="client",
        status="active",
        organization_id="org-once-1",
    )
    u2 = User(
        email="never@test.com",
        password_hash="x",
        full_name="Never",
        role="client",
        status="active",
        organization_id="org-never-1",
    )
    db.add_all([u1, u2])
    db.flush()

    db.add(
        ActivityLog(
            user_id=u1.id,
            actor_user_id=u1.id,
            action="admin.user_suspend",
            message="suspendu",
            level="INFO",
            category="admin",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    items = list_users_ever_suspended(db, limit=10)
    emails = {i.email for i in items}
    assert "once@test.com" in emails
    assert "never@test.com" not in emails
