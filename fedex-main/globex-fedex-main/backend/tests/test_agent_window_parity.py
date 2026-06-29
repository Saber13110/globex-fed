"""Parité fenêtre agent ↔ kernel globex-agent (simple_mode)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.schemas.agent_window import AgentWindowChatRequest
from app.services.admin_client.pipeline import run_admin_client_turn
from app.services.jarvis.agent_window_service import (
    _detect_sensitive_action,
    process_agent_window_chat,
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
        email="admin-window@test.com",
        password_hash="x",
        full_name="Admin",
        role="admin",
        status="active",
        organization_id="org-admin-1",
    )
    db.add(user)
    db.flush()
    return user


def test_sensitive_guard_allows_notifications_and_exports():
    assert not _detect_sensitive_action("donne moi les 5 notifications")
    assert not _detect_sensitive_action("exporte mes notifications en PDF")
    assert not _detect_sensitive_action("mets le suivi en pdf")
    assert _detect_sensitive_action("suspendre le compte utilisateur 42")


@patch("app.services.globex_agent.kernel.run_globex_agent_chat")
def test_agent_window_delegates_to_globex_kernel(mock_kernel, db, admin):
    mock_kernel.return_value = {
        "reply": "Liste notifications",
        "execution_time_ms": 12.5,
        "chat_session_id": 99,
        "intent": "notifications_query",
        "export_download": None,
        "shipment": None,
    }
    payload = AgentWindowChatRequest(message="montre mes notifications", ui_language="fr")
    with patch("app.services.jarvis.agent_window_service.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.globex_simple_mode = True
        settings.prompt_guard_enabled = False
        resp = process_agent_window_chat(db, admin, payload)

    assert resp.engine == "globex-agent"
    assert resp.reply == "Liste notifications"
    assert resp.chat_session_id == 99
    mock_kernel.assert_called_once()


@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_agent_window_and_pipeline_same_notification_intent(
    mock_sync, _ollama, db, admin
):
    """process_agent_window_chat et run_admin_client_turn partagent le même intent."""
    del mock_sync
    from datetime import datetime, timezone

    from app.models.platform_notification import PlatformNotification

    db.add(
        PlatformNotification(
            external_key="parity-1",
            category="colis",
            title="Alerte colis",
            message="Retard",
            priority="high",
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    direct = run_admin_client_turn(db, admin, "donne moi les 5 notifications", ui_language="fr")
    assert direct is not None
    assert direct["intent"] == "notifications_query"

    with patch("app.services.jarvis.agent_window_service.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.globex_simple_mode = True
        settings.prompt_guard_enabled = False
        payload = AgentWindowChatRequest(message="donne moi les 5 notifications", ui_language="fr")
        window = process_agent_window_chat(db, admin, payload)

    assert window.engine == "globex-agent"
    assert "Alerte colis" in window.reply or "notification" in window.reply.lower()
    assert window.redirect_to_copilot is False
