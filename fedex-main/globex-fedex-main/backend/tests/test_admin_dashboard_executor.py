"""Tests exécuteur dashboard admin."""

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
from app.services.admin_client.dashboard.dashboard_executor import try_admin_dashboard_turn


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


def _summary(open_incidents: int = 2) -> dict:
    return {
        "lang": "fr",
        "period": "today",
        "shipments_today": 44,
        "delivered_today": 1,
        "in_transit": 13,
        "delayed_shipments": 1,
        "blocked_shipments": 0,
        "active_users": 12,
        "online_users": 5,
        "total_users": 12,
        "open_incidents": open_incidents,
        "fedex_requests_today": 0,
        "fedex_error_rate": 0.01,
        "system_health": [],
        "recent_activity": [],
        "anomalies": [f"{open_incidents} incident(s) ouvert(s)"] if open_incidents else [],
        "data_quality": {"has_inconsistency": False, "inconsistencies": []},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@patch("app.services.admin_client.dashboard.dashboard_snapshot.fetch_command_center_and_summary")
def test_executor_platform_overview_facts(mock_fetch, db, admin, chat_session):
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
            requests_today=0, success_rate=1, latency_ms=0, error_rate=0, requests_series=[]
        ),
        activity_timeline=[],
        open_incidents=2,
        notification_count=0,
        total_users=12,
        generated_at=now,
    )
    mock_fetch.return_value = (cc, _summary(2))

    out = try_admin_dashboard_turn(
        db, admin, chat_session, "Résume l'état de la plateforme", 1, "fr"
    )
    assert out is not None
    assert out["source"] == "admin_dashboard"
    assert out["tool_used"] == "get_dashboard_summary"
    assert out["tool_called"] is True
    assert "introduction professionnelle" not in out["reply"].lower()
    assert "44" in out["reply"]
    assert out["reply"].count("Incidents ouverts") <= 1
    assert "Source : Dashboard Admin" in out["reply"]


@patch("app.services.admin_client.dashboard.dashboard_snapshot.fetch_command_center_and_summary")
def test_executor_delayed_shipments(mock_fetch, db, admin, chat_session):
    from app.schemas.command_center import (
        CommandCenterPayload,
        FedexApiMetrics,
        LiveShipmentItem,
    )

    now = datetime.now(timezone.utc)
    cc = CommandCenterPayload(
        hero_stats=[],
        today_overview=[],
        executive_insights=[],
        kpis=[],
        live_shipments=[
            LiveShipmentItem(
                id=1,
                route="A → B",
                origin="A",
                destination="B",
                origin_flag="🇫🇷",
                destination_flag="🇫🇷",
                carrier="FedEx",
                tracking_number="817950452196",
                status="Delayed",
                status_key="delayed",
                eta_label="Demain",
                progress_percent=30,
                updated_at=now,
            )
        ],
        recent_conversations=[],
        system_health=[],
        user_roles=[],
        pending_invitations=0,
        recent_users=[],
        fedex_metrics=FedexApiMetrics(
            requests_today=0, success_rate=1, latency_ms=0, error_rate=0, requests_series=[]
        ),
        activity_timeline=[],
        open_incidents=0,
        notification_count=0,
        total_users=10,
        generated_at=now,
    )
    s = _summary(0)
    s["delayed_shipments"] = 1
    s["delayed_shipments_detail"] = [
        {
            "tracking_number": "817950452196",
            "status": "Delayed",
            "route": "A → B",
            "eta_label": "Demain",
        }
    ]
    mock_fetch.return_value = (cc, s)

    out = try_admin_dashboard_turn(
        db, admin, chat_session, "Quels colis en retard ?", 1, "fr"
    )
    assert out is not None
    assert out["intent"] == "dashboard_delays"
    assert "817950452196" in out["reply"]


def test_executor_skips_tracking(db, admin, chat_session):
    out = try_admin_dashboard_turn(
        db, admin, chat_session, "suivi 817725683025", 1, "fr"
    )
    assert out is None
