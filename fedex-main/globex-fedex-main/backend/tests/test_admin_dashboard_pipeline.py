"""Tests pipeline dashboard — outils obligatoires avant LLM."""

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
from app.services.admin_client.dashboard.dashboard_pipeline import (
    detect_intent,
    execute_tools,
    process_results_with_tools,
    run_dashboard_pipeline,
    select_required_tools,
    validate_tool_results,
)
from app.services.admin_client.dashboard.dashboard_processors import (
    classify_dashboard_priorities,
    summarize_recent_activity,
    validate_dashboard_data,
)
from app.services.admin_client.dashboard.dashboard_types import DashboardQuestionType  # noqa: F401


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


def _summary() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "lang": "fr",
        "period": "today",
        "shipments_today": 44,
        "delivered_today": 1,
        "in_transit": 13,
        "delayed_shipments": 2,
        "blocked_shipments": 0,
        "active_users": 12,
        "online_users": 5,
        "total_users": 12,
        "open_incidents": 1,
        "fedex_requests_today": 20,
        "fedex_error_rate": 0.01,
        "system_health": [],
        "recent_activity": [
            {"time_label": "10:00", "level": "ERROR", "message": "FedEx timeout"},
        ],
        "anomalies": [],
        "data_quality": {"has_inconsistency": False, "inconsistencies": []},
        "generated_at": now.isoformat(),
    }


def test_select_required_tools_includes_mandatory_fetch():
    plan = detect_intent("Quels sont les principaux KPIs ?", ui_language="fr")
    assert plan is not None
    tools = select_required_tools(plan)
    assert "get_dashboard_summary" in tools
    assert "validate_dashboard_data" in tools
    assert "detect_dashboard_anomalies" in tools


def test_validate_dashboard_data_flags_missing():
    result = validate_dashboard_data({"lang": "fr", "shipments_today": 10})
    assert result["valid"] is False
    assert "delivered_today" in result["missing_fields"]


def test_classify_priorities_orders_incidents_first():
    data = _summary()
    items = classify_dashboard_priorities(data)
    assert items[0]["kpi"] == "open_incidents"


def test_summarize_recent_activity_structure():
    digest = summarize_recent_activity(_summary())
    assert digest["total_events"] == 1
    assert digest["has_errors"] is True


@patch("app.services.admin_client.dashboard.dashboard_snapshot.fetch_command_center_and_summary")
def test_pipeline_metadata_and_tools(mock_fetch, db, admin, chat_session):
    from app.schemas.command_center import CommandCenterPayload, FedexApiMetrics

    now = datetime.now(timezone.utc)
    cc = CommandCenterPayload(
        hero_stats=[],
        today_overview=[],
        executive_insights=[],
        kpis=[],
        live_shipments=[],
        recent_conversations=[],
        system_health=[],
        user_roles=[],
        pending_invitations=0,
        recent_users=[],
        fedex_metrics=FedexApiMetrics(
            requests_today=20, success_rate=1, latency_ms=0, error_rate=0.01, requests_series=[]
        ),
        activity_timeline=[],
        open_incidents=1,
        notification_count=0,
        total_users=12,
        generated_at=now,
    )
    mock_fetch.return_value = (cc, _summary())

    out = run_dashboard_pipeline(
        db, admin, chat_session, "Résume l'état de la plateforme", 1, "fr"
    )
    assert out is not None
    assert out["tool_called"] is True
    assert out["tool_used"] == "get_dashboard_summary"
    assert out["raw_data_received"] is True
    assert out["data_source"] == "admin_dashboard_api"
    assert "44" in out["reply"] or "1" in out["reply"]
    labels = [s["label"] for s in out["agent_steps"]]
    assert "get_dashboard_summary" in labels
    assert "validate_dashboard_data" in labels


@patch("app.services.admin_client.dashboard.dashboard_snapshot.fetch_command_center_and_summary")
def test_pipeline_fetch_failure_no_numeric_reply(mock_fetch, db, admin, chat_session):
    from app.services.admin_client.dashboard.dashboard_tool import DashboardSummaryError

    mock_fetch.side_effect = DashboardSummaryError("db down")
    out = run_dashboard_pipeline(
        db, admin, chat_session, "État de la plateforme", 1, "fr"
    )
    assert out is not None
    assert out["raw_data_received"] is False
    assert "réponse fiable" in out["reply"].lower()
    assert out["confidence"] == "low"


def test_process_results_enriches_summary():
    plan = detect_intent("activité récente", ui_language="fr")
    assert plan is not None
    processed = process_results_with_tools(_summary(), plan)
    assert "priorities" in processed
    assert "activity_digest" in processed["summary"]
    assert processed["summary"]["validation"]["valid"] is True
