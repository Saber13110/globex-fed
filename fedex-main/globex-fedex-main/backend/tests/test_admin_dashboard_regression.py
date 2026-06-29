"""Régression kernel — questions KPI via admin_dashboard, pas Ollama."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base
from app.models.user import User
from app.schemas.command_center import CommandCenterPayload, FedexApiMetrics, HeroStatItem
from app.services.admin_client.pipeline import run_admin_client_turn
from app.services.globex_agent import kernel as kernel_mod


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


def _mock_cc() -> CommandCenterPayload:
    now = datetime.now(timezone.utc)
    return CommandCenterPayload(
        hero_stats=[HeroStatItem(label="Expéditions", value=77, icon="package")],
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
            requests_today=20,
            success_rate=0.99,
            latency_ms=90,
            error_rate=0.01,
            requests_series=[],
        ),
        activity_timeline=[],
        open_incidents=0,
        notification_count=0,
        total_users=4,
        generated_at=now,
    )


@patch("app.services.admin_client.dashboard.dashboard_snapshot.fetch_command_center_and_summary")
@patch("app.services.globex_agent.kernel.admin_ollama_chat")
def test_pipeline_kpi_dashboard_not_none(mock_ollama, mock_fetch, db, admin):
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
            requests_today=20, success_rate=0.99, latency_ms=90, error_rate=0.01, requests_series=[]
        ),
        activity_timeline=[],
        open_incidents=0,
        notification_count=0,
        total_users=4,
        generated_at=now,
    )
    mock_fetch.return_value = (
        cc,
        {
            "shipments_today": 77,
            "delivered_today": 0,
            "in_transit": 10,
            "active_users": 4,
            "total_users": 4,
            "open_incidents": 0,
            "fedex_requests_today": 20,
            "fedex_error_rate": 0.01,
            "system_health": [],
            "recent_activity": [],
            "anomalies": [],
            "data_quality": {"has_inconsistency": False, "inconsistencies": []},
            "lang": "fr",
        },
    )

    result = run_admin_client_turn(
        db, admin, "État de la plateforme aujourd'hui", ui_language="fr"
    )
    assert result is not None
    assert "77" in result["reply"]
    assert result.get("tool_used") == "get_dashboard_summary"
    assert result.get("intent") == "dashboard_overview"
    mock_ollama.assert_not_called()


@patch("app.services.admin_client.dashboard.dashboard_snapshot.fetch_command_center_and_summary")
@patch("app.services.globex_agent.kernel.admin_ollama_chat")
def test_kernel_kpi_uses_dashboard_not_ollama(
    mock_ollama, mock_fetch, db, admin
):
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
            requests_today=20, success_rate=0.99, latency_ms=90, error_rate=0.01, requests_series=[]
        ),
        activity_timeline=[],
        open_incidents=0,
        notification_count=0,
        total_users=4,
        generated_at=now,
    )
    mock_fetch.return_value = (
        cc,
        {
            "shipments_today": 77,
            "delivered_today": 0,
            "in_transit": 10,
            "active_users": 4,
            "total_users": 4,
            "open_incidents": 0,
            "fedex_requests_today": 20,
            "fedex_error_rate": 0.01,
            "system_health": [],
            "recent_activity": [],
            "anomalies": [],
            "data_quality": {"has_inconsistency": False, "inconsistencies": []},
            "lang": "fr",
        },
    )

    from app.services.globex_agent.kernel import run_globex_agent_chat

    with patch("app.services.globex_agent.kernel.get_settings") as mock_settings:
        settings = mock_settings.return_value
        settings.globex_simple_mode = True
        settings.llm_enabled = True

        result = run_globex_agent_chat(
            db,
            admin,
            "KPI plateforme aujourd'hui",
            ui_language="fr",
            agent_mode=True,
        )
    mock_ollama.assert_not_called()
    assert result is not None
    assert "77" in result.get("reply", "")
