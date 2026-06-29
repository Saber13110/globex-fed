"""Tests agent Security IDS admin — Phase 1."""

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
from app.models.security_incident import SecurityIncident
from app.models.user import User
from app.services.admin_client.intent_priority import (
    should_route_logs,
    should_route_security,
    should_route_tickets,
)
from app.services.admin_client.security.security_followup import (
    extract_incident_ref,
    resolve_incident_id_from_context,
)
from app.services.admin_client.security.security_intent import classify_security_intent
from app.services.admin_client.security.security_patterns import is_logs_anomaly_scope
from app.services.admin_client.security.security_types import SecurityTaskType
from app.services.admin_client.security.security_executor import try_admin_security_turn
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
        email="admin-sec@test.com",
        password_hash="x",
        full_name="Admin Sec",
        role="admin",
        status="active",
        organization_id="org-admin-sec",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client_user(db):
    user = User(
        email="client-sec@test.com",
        password_hash="x",
        full_name="Client Sec",
        role="client",
        status="active",
        organization_id="org-client-sec",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def chat_session(db, admin):
    sess = ChatSession(user_id=admin.id, title="Security test")
    db.add(sess)
    db.flush()
    return sess


def test_logs_anomaly_deferred_to_logs_agent():
    assert is_logs_anomaly_scope("détecte les anomalies dans les logs")
    assert not should_route_security("détecte les anomalies dans les logs")
    assert should_route_logs("détecte les anomalies dans les logs")


def test_security_scan_intent():
    plan = classify_security_intent("lance un scan IDS")
    assert plan.task_type == SecurityTaskType.security_scan


def test_security_list_open_intent():
    plan = classify_security_intent("liste les incidents ouverts")
    assert plan.task_type == SecurityTaskType.security_incident_list
    assert plan.status_filter == "active"


def test_security_summary_intent():
    plan = classify_security_intent("résume les incidents ouverts")
    assert plan.task_type == SecurityTaskType.security_incident_summary


def test_security_report_intent():
    plan = classify_security_intent("génère un rapport sécurité")
    assert plan.task_type == SecurityTaskType.security_report


def test_incidents_not_routed_to_tickets():
    hist = (
        "**Incidents sécurité** (active)\n"
        "| 12 | 2026-06-29 | high | prompt_injection | open | a@b.com | titre |\n"
        "| 11 | 2026-06-29 | medium | brute_force | open | b@b.com | titre2 |"
    )
    assert not should_route_tickets("detaille incident #2", history_text=hist)
    assert should_route_security("detaille incident #2", history_text=hist)
    assert extract_ticket_ref("detaille incident #2", history_text=hist) is None


def test_row_resolution(db, client_user):
    now = datetime.now(timezone.utc)
    for iid, title in ((12, "Inc A"), (11, "Inc B")):
        db.add(
            SecurityIncident(
                id=iid,
                dedupe_key=f"test-{iid}",
                user_id=client_user.id,
                source="rule_engine",
                threat_type="prompt_injection",
                severity="high",
                score=80,
                title=title,
                summary="Test",
            )
        )
    db.commit()

    hist = (
        "**Incidents sécurité**\n"
        "| 12 | 2026-01-01 | high | prompt_injection | open | a@b.com | Inc A |\n"
        "| 11 | 2026-01-01 | medium | brute_force | open | b@b.com | Inc B |"
    )
    assert extract_incident_ref("detail incident #11", history_text=hist) == 11
    assert extract_incident_ref("detail incident #2", history_text=hist) == 11
    assert resolve_incident_id_from_context(db, 11, history_text=hist) == 11


def test_incident_id_not_row_when_in_list(db, client_user):
    now = datetime.now(timezone.utc)
    for iid in (12, 11, 3):
        db.add(
            SecurityIncident(
                id=iid,
                dedupe_key=f"test-id-{iid}",
                user_id=client_user.id,
                source="rule_engine",
                threat_type="prompt_injection",
                severity="high",
                score=80,
                title=f"Inc {iid}",
                summary="Test",
            )
        )
    db.commit()
    hist = (
        "**Incidents sécurité**\n"
        "| 12 | 2026-01-01 | high | x | open | a@b.com | A |\n"
        "| 11 | 2026-01-01 | high | x | open | a@b.com | B |\n"
        "| 3 | 2026-01-01 | high | x | open | a@b.com | C |"
    )
    assert extract_incident_ref("detail incident #3", history_text=hist) == 3
    assert resolve_incident_id_from_context(db, 3, history_text=hist) == 3


def test_resume_incident_not_dashboard():
    assert should_route_security("resume incident ouvert")
    from app.services.admin_client.intent_priority import should_route_dashboard

    assert not should_route_dashboard("resume incident ouvert")


def test_security_report_routing():
    assert should_route_security("je veux que tu me donne un rapport de securite")
    plan = classify_security_intent("je veux que tu me donne un rapport de securite")
    assert plan.task_type == SecurityTaskType.security_report


def test_security_pdf_followup_detection():
    hist = "**Incidents sécurité**\n| 12 | 2026-01-01 | high | x | open | a@b.com | A |"
    from app.services.admin_client.security.security_pdf import is_security_pdf_followup

    assert is_security_pdf_followup(
        "je veux un rapport de securite dans un fichier pdf", history_text=hist
    )


@patch("app.services.admin_client.security.security_tool.list_incidents")
def test_pipeline_list(mock_list, db, admin, chat_session):
    mock_list.return_value = {
        "incidents": [
            {
                "id": 1,
                "severity": "high",
                "threat_type": "prompt_injection",
                "status": "open",
                "title": "Test",
                "user_email": "x@test.com",
                "created_at": datetime.now(timezone.utc),
            }
        ],
        "total": 1,
        "open_count": 1,
    }
    out = try_admin_security_turn(
        db, admin, chat_session, "liste incidents ouverts", 1, "fr"
    )
    assert out is not None
    assert out["intent"] == "security_incidents_list"
    assert "prompt_injection" in out["reply"]


@patch("app.services.admin_client.security.security_tool.run_scan")
def test_pipeline_scan(mock_scan, db, admin, chat_session):
    mock_scan.return_value = {
        "rules_incidents": 2,
        "ai_incidents": 0,
        "include_ai": False,
        "open_count": 5,
    }
    out = try_admin_security_turn(
        db, admin, chat_session, "lance scan IDS", 1, "fr"
    )
    assert out is not None
    assert out["intent"] == "security_ids_scan"
    assert "2" in out["reply"]
