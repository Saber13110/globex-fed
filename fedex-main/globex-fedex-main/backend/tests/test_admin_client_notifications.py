"""Tests notifications admin — parité Phase 5 sur PlatformNotification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.platform_notification import PlatformNotification
from app.models.user import User
from app.services.admin_client.admin_notification_plan import (
    extract_admin_notification_limit,
    reconcile_admin_notification_plan,
)
from app.services.admin_client.admin_notification_summary import (
    generate_admin_platform_notifications_summary,
)
from app.services.admin_client.pipeline import run_admin_client_turn
from app.services.admin_client.platform_notification_fetch import (
    fetch_platform_notifications_for_query,
    mark_all_platform_notifications_read,
    platform_item_to_user_read,
)
from app.services.client_phase5.notification_filters import NotificationQueryParams


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
        email="admin-notif@test.com",
        password_hash="x",
        full_name="Admin",
        role="admin",
        status="active",
        organization_id="org-admin-1",
    )
    db.add(user)
    db.flush()
    return user


def _seed_platform_notifications(db, *, admin_id: int = 1) -> None:
    now = datetime.now(timezone.utc)
    rows = [
        PlatformNotification(
            external_key="test-colis-1",
            category="colis",
            title="Retard colis",
            message="Le colis 881135077232 est en retard",
            tracking_number="881135077232",
            priority="high",
            is_read=False,
            created_at=now - timedelta(hours=1),
        ),
        PlatformNotification(
            external_key="test-incident-1",
            category="incidents",
            title="Ticket support urgent",
            message="Nouveau message client",
            priority="high",
            is_read=False,
            created_at=now - timedelta(hours=2),
        ),
        PlatformNotification(
            external_key="test-ia-1",
            category="ia",
            title="Rapport IA",
            message="Synthèse hebdomadaire disponible",
            priority="normal",
            is_read=True,
            created_at=now - timedelta(days=10),
        ),
    ]
    for row in rows:
        db.add(row)
    db.commit()


@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_fetch_platform_tracking_section_and_limit(mock_sync, db, admin):
    del mock_sync
    _seed_platform_notifications(db)
    params = NotificationQueryParams(section="tracking", limit=5)
    result = fetch_platform_notifications_for_query(db, admin.id, params)
    assert len(result.items) == 1
    assert result.items[0].type == "tracking_update"
    assert result.items[0].related_tracking_number == "881135077232"


@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_fetch_platform_since_days(mock_sync, db, admin):
    del mock_sync
    _seed_platform_notifications(db)
    params = NotificationQueryParams(since_days=7, limit=50)
    result = fetch_platform_notifications_for_query(db, admin.id, params)
    assert len(result.items) == 2
    assert result.unread_count == 2


@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_fetch_platform_unread_status(mock_sync, db, admin):
    del mock_sync
    _seed_platform_notifications(db)
    params = NotificationQueryParams(status="unread", limit=50)
    result = fetch_platform_notifications_for_query(db, admin.id, params)
    assert len(result.items) == 2
    assert all(not item.is_read for item in result.items)


def test_platform_item_to_user_read_mapping():
    row = PlatformNotification(
        id=1,
        external_key="x",
        category="colis",
        title="T",
        message="M",
        tracking_number="123",
        route="/admin/notifications",
        priority="high",
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )
    item = platform_item_to_user_read(row, admin_id=99)
    assert item.user_id == 99
    assert item.type == "tracking_update"
    assert item.related_tracking_number == "123"


def test_extract_admin_notification_limit_french_words():
    assert extract_admin_notification_limit("derniers deux notifications") == 2
    assert extract_admin_notification_limit("donne les trois dernieres notifs") == 3
    assert extract_admin_notification_limit("liste mes 5 notifications") == 5


def test_reconcile_admin_forces_list_over_ollama_summarize():
    plan = reconcile_admin_notification_plan(
        "donne les deux notifications",
        {
            "task_type": "notifications_query",
            "answers": {"mode": "summarize", "limit": 15, "attach_pdf": False},
            "needs_clarification": False,
        },
    )
    assert plan["answers"]["mode"] == "list"
    assert plan["answers"]["limit"] == 2


def test_admin_factual_summary_platform_wording():
    from app.schemas.user_notifications import UserNotificationRead

    now = datetime.now(timezone.utc)
    items = [
        UserNotificationRead(
            id=1,
            user_id=1,
            type="system_alert",
            title="System Event",
            message="Export PDF texte client (doc.pdf)",
            status="unread",
            is_read=False,
            created_at=now,
        ),
    ]
    text = generate_admin_platform_notifications_summary(items, lang="fr")
    assert "plateforme" in text.lower()
    assert "System Event" in text
    assert "Le client avait" not in text
    assert "Prêt pour le ramassage" not in text


@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_admin_donne_les_deux_dernieres_notifications(mock_sync, _ollama, db, admin):
    del mock_sync
    now = datetime.now(timezone.utc)
    for i in range(3):
        db.add(
            PlatformNotification(
                external_key=f"two-limit-{i}",
                category="system",
                title="System Event",
                message=f"Export PDF texte client (file-{i}.pdf)",
                priority="normal",
                is_read=False,
                created_at=now - timedelta(minutes=i),
            )
        )
    db.commit()

    result = run_admin_client_turn(
        db,
        admin,
        "je veux que tu me donne les derniers deux notifications",
        ui_language="fr",
    )
    assert result is not None
    assert result["intent"] == "notifications_query"
    assert result["reply"].count("System Event") == 2
    assert "Prêt pour le ramassage" not in result["reply"]


@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_admin_workspace_never_returns_none_to_kernel(mock_sync, _ollama, db, admin):
    del mock_sync
    result = run_admin_client_turn(db, admin, "montre mes notifications", ui_language="fr")
    assert result is not None
    assert result["intent"] == "notifications_query"


@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_admin_list_notifications_fallback(mock_sync, _ollama, db, admin):
    del mock_sync
    _seed_platform_notifications(db)
    result = run_admin_client_turn(db, admin, "montre mes notifications", ui_language="fr")
    assert result is not None
    assert result["intent"] == "notifications_query"
    assert "Retard colis" in result["reply"] or "notification" in result["reply"].lower()


@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_admin_unread_notifications(mock_sync, _ollama, db, admin):
    del mock_sync
    _seed_platform_notifications(db)
    result = run_admin_client_turn(
        db, admin, "mes notifications non lues", ui_language="fr"
    )
    assert result is not None
    assert result["intent"] == "notifications_query"


@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_admin_summarize_notifications(mock_sync, _ollama, db, admin):
    del mock_sync
    _seed_platform_notifications(db)
    result = run_admin_client_turn(
        db, admin, "résume mes alertes colis", ui_language="fr"
    )
    assert result is not None
    assert result["intent"] == "notifications_query"
    assert "Synthèse plateforme" in result["reply"] or "plateforme" in result["reply"].lower()


@patch("app.services.client_phase5.notification_executor.has_capability", return_value=True)
@patch("app.services.client_phase5.notification_executor.build_notifications_pdf_artifact")
@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_admin_export_notifications_pdf(
    mock_sync, _ollama, mock_pdf, _cap, db, admin
):
    del mock_sync, _cap
    _seed_platform_notifications(db)
    mock_pdf.return_value = (
        {
            "preset": "notifications_pdf",
            "filename": "notifications.pdf",
            "format": "pdf",
            "export_token": "toknotif01",
            "session_id": 1,
        },
        b"%PDF",
        "notifications.pdf",
    )
    result = run_admin_client_turn(
        db, admin, "exporte mes notifications en PDF", ui_language="fr"
    )
    assert result is not None
    assert result["intent"] == "export_notifications_pdf"
    assert result["export_download"]["preset"] == "notifications_pdf"
    mock_pdf.assert_called_once()


@patch("app.services.notifications_service.mark_all_read", return_value=3)
@patch("app.services.client_phase5.router._call_ollama_notifications_plan")
def test_admin_mark_all_read(mock_ollama, mock_mark, db, admin):
    mock_ollama.return_value = {
        "task_type": "notifications_mark_all_read",
        "assistant_intro": "",
        "answers": {},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    result = run_admin_client_turn(
        db, admin, "marque toutes mes notifications comme lues", ui_language="fr"
    )
    assert result is not None
    assert result["intent"] == "notifications_mark_all_read"
    assert "3" in result["reply"]
    mock_mark.assert_called_once()


@patch("app.services.client_phase5.router._call_ollama_notifications_plan")
def test_admin_clarification_ambiguous_read(mock_ollama, db, admin):
    mock_ollama.return_value = {
        "task_type": "notifications_query",
        "assistant_intro": "",
        "answers": {"mode": "list"},
        "ready_to_execute": True,
        "needs_clarification": False,
        "clarification_question": "",
    }
    result = run_admin_client_turn(
        db,
        admin,
        "je veux que tu me rend les notifications comme deja lu",
        ui_language="fr",
    )
    assert result is not None
    assert "?" in result["reply"] or "voir" in result["reply"].lower()


@patch("app.services.notifications_service.mark_all_read", return_value=2)
def test_mark_all_platform_notifications_read(mock_mark, db, admin):
    count = mark_all_platform_notifications_read(db, admin.id)
    assert count == 2
    mock_mark.assert_called_once()


@patch("app.services.client_phase5.router._call_ollama_notifications_plan", return_value=None)
@patch("app.services.admin_client.platform_notification_fetch.sync_notifications")
def test_notifications_win_over_document_followup_with_pdf_in_session(
    mock_sync, _ollama, db, admin
):
    """« donne moi les 5 notifications » ne doit pas être traité comme question PDF."""
    del mock_sync
    from app.services.admin_client.session_bridge import (
        get_or_create_chat_session,
        persist_bot_message,
        persist_user_message,
    )

    _seed_platform_notifications(db)
    session = get_or_create_chat_session(db, admin)
    persist_user_message(
        db,
        session,
        "résume ce document",
        image_base64="Zm9v",
        image_mime_type="application/pdf",
        file_name="facture.pdf",
    )
    persist_bot_message(db, session, "Le document ne contient pas d'informations sur les notifications.")
    db.commit()

    result = run_admin_client_turn(
        db,
        admin,
        "donne moi les 5 notifications",
        ui_language="fr",
        chat_session_id=session.id,
    )
    assert result is not None
    assert result["intent"] == "notifications_query"
    assert "document ne contient pas" not in result["reply"].lower()
    assert "Retard colis" in result["reply"] or "notification" in result["reply"].lower()
