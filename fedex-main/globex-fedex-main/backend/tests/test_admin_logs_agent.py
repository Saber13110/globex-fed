"""Tests agent Logs admin."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.activity_log import ActivityLog
from app.models.chat_session import ChatSession
from app.models.user import User
from app.services.admin_client.intent_priority import (
    should_route_logs,
    should_route_tickets,
    should_route_users,
)
from app.services.admin_client.logs.logs_followup import extract_log_ref, resolve_log_id_from_context
from app.services.admin_client.logs.logs_intent import classify_logs_intent
from app.services.admin_client.logs.logs_patterns import is_user_scoped_logs_message
from app.services.admin_client.logs.logs_export import (
    is_logs_excel_followup,
    is_logs_pdf_followup,
    resolve_logs_export_format,
)
from app.services.admin_client.logs.logs_types import LogsTaskType
from app.services.admin_client.logs.logs_executor import try_admin_logs_turn
from app.services.admin_client.tickets.tickets_followup import extract_ticket_ref


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
        email="admin-logs@test.com",
        password_hash="x",
        full_name="Admin Logs",
        role="admin",
        status="active",
        organization_id="org-admin-logs",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client_user(db):
    user = User(
        email="client-logs@test.com",
        password_hash="x",
        full_name="Client Logs",
        role="client",
        status="active",
        organization_id="org-client-logs",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def chat_session(db, admin):
    sess = ChatSession(user_id=admin.id, title="Logs test")
    db.add(sess)
    db.flush()
    return sess


def test_user_scoped_logs_deferred_to_users_agent():
    assert is_user_scoped_logs_message("logs de l'utilisateur abdo@gmail.com")
    assert not should_route_logs("logs de l'utilisateur abdo@gmail.com")
    assert should_route_users("logs de l'utilisateur abdo@gmail.com")


def test_global_logs_routed():
    assert should_route_logs("liste les journaux d'activité des dernières 24h")
    assert not should_route_users("liste les journaux d'activité des dernières 24h")


def test_intent_list_warning():
    plan = classify_logs_intent("liste les logs WARNING des dernières 24h")
    assert plan.task_type == LogsTaskType.log_list
    assert plan.level_filter == "WARNING"


def test_intent_anomalies():
    plan = classify_logs_intent("détecte les anomalies dans les logs")
    assert plan.task_type == LogsTaskType.log_anomalies


def test_intent_summary_user_email():
    plan = classify_logs_intent("resume activite amine@gmail.com")
    assert plan.task_type == LogsTaskType.log_summary_user_day
    assert plan.user_query == "amine@gmail.com"


def test_intent_summary_platform_today():
    plan = classify_logs_intent("resumer l'activite du jour")
    assert plan.task_type == LogsTaskType.log_summary_platform_day


def test_logs_not_routed_to_tickets():
    hist = (
        "**Journal d'activité** (48h)\n"
        "| 3329 | 2026-06-29 | INFO | globex_proactive.scan | — | scan |\n"
        "| 3328 | 2026-06-29 | INFO | globex_proactive.scan | — | scan2 |"
    )
    assert not should_route_tickets("ouvert moi le log #3328", history_text=hist)
    assert should_route_logs("detaille de log #2", history_text=hist)
    assert extract_ticket_ref("detaille de log #2", history_text=hist) is None
    plan = classify_logs_intent("detaille de log #2", history_text=hist)
    assert plan.task_type == LogsTaskType.log_detail


def test_logs_pdf_followup():
    hist = "**Journal d'activité** (48h)\n| 1 | 2026-01-01 | INFO | auth.login | a@b.com | msg |"
    assert is_logs_pdf_followup("je veux que tu me donne dans un fichier pdf", history_text=hist)
    assert not is_logs_pdf_followup(
        "je veux que tu me donne en fichier excel les logs", history_text=hist
    )
    assert is_logs_excel_followup(
        "je veux que tu me donne en fichier excel les logs", history_text=hist
    )


def test_logs_export_format_resolution():
    assert resolve_logs_export_format("donne les logs en excel des 24h") == "xlsx"
    assert resolve_logs_export_format("donne les logs en pdf des 24h") == "pdf"
    assert resolve_logs_export_format("excel et pdf logs 24h") is None


def test_intent_excel_logs_24h():
    plan = classify_logs_intent("je veux que tu me donne en fichier excel les logs de dernier 24h")
    assert plan.task_type == LogsTaskType.log_list
    assert plan.want_excel is True
    assert plan.want_pdf is False
    assert plan.period_hours == 24


def test_intent_pdf_logs_24h():
    plan = classify_logs_intent("je veux que tu me donne en fichier pdf les logs de dernier 24h")
    assert plan.task_type == LogsTaskType.log_list
    assert plan.want_pdf is True
    assert plan.want_excel is False


def test_intent_excel_pdf_conflict_clarify():
    plan = classify_logs_intent(
        "je veux que tu me donne en fichier excel les logs de dernier 24h en pdf"
    )
    assert plan.needs_clarification is True
    assert "Excel" in plan.clarification_question
    assert "PDF" in plan.clarification_question


@patch("app.services.admin_client.logs.logs_export.build_logs_excel_export")
@patch("app.services.admin_client.logs.logs_tool.list_logs")
def test_pipeline_excel_export_direct(mock_list, mock_excel, db, admin, chat_session):
    mock_list.return_value = {
        "logs": [
            {
                "id": 1,
                "level": "INFO",
                "action": "auth.login",
                "message": "OK",
                "user_email": "x@test.com",
                "created_at": datetime.now(timezone.utc),
            }
        ],
        "total": 1,
    }
    mock_excel.return_value = (
        "Votre fichier Excel des journaux est prêt — utilisez le lien de téléchargement ci-dessous.",
        {"preset": "admin_logs", "filename": "activity-logs-24h.xlsx", "format": "xlsx"},
    )
    out = try_admin_logs_turn(
        db,
        admin,
        chat_session,
        "je veux que tu me donne en fichier excel les logs de dernier 24h",
        1,
        "fr",
    )
    assert out is not None
    assert out["export_download"]["format"] == "xlsx"
    assert "Excel" in out["reply"]
    mock_excel.assert_called_once()


@patch("app.services.admin_client.logs.logs_export.build_logs_pdf_export")
@patch("app.services.admin_client.logs.logs_tool.list_logs")
def test_pipeline_pdf_export_direct(mock_list, mock_pdf, db, admin, chat_session):
    mock_list.return_value = {
        "logs": [{"id": 1, "level": "INFO", "action": "auth.login", "message": "OK"}],
        "total": 1,
    }
    mock_pdf.return_value = (
        "Votre PDF journaux est prêt — utilisez le lien de téléchargement ci-dessous.",
        {"preset": "admin_logs", "filename": "activity-logs-24h.pdf", "format": "pdf"},
    )
    out = try_admin_logs_turn(
        db,
        admin,
        chat_session,
        "je veux que tu me donne en fichier pdf les logs de dernier 24h",
        1,
        "fr",
    )
    assert out is not None
    assert out["export_download"]["format"] == "pdf"
    mock_pdf.assert_called_once()


def test_row_resolution(db, client_user):
    now = datetime.now(timezone.utc)
    for lid, action in ((100, "auth.login"), (99, "chat.user_message")):
        db.add(
            ActivityLog(
                id=lid,
                user_id=client_user.id,
                level="INFO",
                category="auth" if "auth" in action else "chat",
                action=action,
                message=f"Event {lid}",
                created_at=now,
            )
        )
    db.commit()

    hist = (
        "**Journal d'activité**\n"
        "| 100 | 2026-01-01 | INFO | auth.login | a@b.com | msg |\n"
        "| 99 | 2026-01-01 | INFO | chat.user_message | a@b.com | msg2 |"
    )
    assert resolve_log_id_from_context(db, 2, history_text=hist) == 99
    assert extract_log_ref("detail du log #2", history_text=hist) == 99


@patch("app.services.admin_client.logs.logs_tool.list_logs")
def test_pipeline_list(mock_list, db, admin, chat_session):
    mock_list.return_value = {
        "logs": [
            {
                "id": 1,
                "level": "WARNING",
                "action": "auth.login_failed",
                "message": "Échec",
                "user_email": "x@test.com",
                "created_at": datetime.now(timezone.utc),
            }
        ],
        "total": 1,
    }
    out = try_admin_logs_turn(
        db, admin, chat_session, "liste les logs WARNING", 1, "fr"
    )
    assert out is not None
    assert out["intent"] == "logs_list"
    assert "auth.login_failed" in out["reply"]


@patch("app.services.admin_client.users.users_service.suspend_user_account")
def test_pipeline_confirm_suspend_from_log(
    mock_suspend, db, admin, chat_session, client_user
):
    mock_suspend.return_value = {"email": client_user.email}
    db.add(
        ActivityLog(
            id=50,
            user_id=client_user.id,
            level="WARNING",
            category="security",
            action="security.chat_probe",
            message="Tentative suspecte",
        )
    )
    db.commit()

    turn1 = try_admin_logs_turn(
        db,
        admin,
        chat_session,
        "suspend l'utilisateur de ce log",
        1,
        "fr",
        history_text="**Fiche log**\n#50 — security.chat_probe",
        conversation_history=[{"role": "assistant", "content": "**Fiche log**\n#50"}],
    )
    assert turn1 is not None
    assert "oui ou non" in turn1["reply"].lower()
    assert turn1["intent"] == "logs_suspend"

    hist = turn1["reply"]
    turn2 = try_admin_logs_turn(
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
    assert turn2["intent"] == "logs_suspend_done"
    mock_suspend.assert_called_once()
