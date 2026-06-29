"""Tests get_dashboard_summary — schéma canonique."""

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
from app.schemas.command_center import (
    CommandCenterPayload,
    FedexApiMetrics,
    HeroStatItem,
    LiveShipmentItem,
    OverviewMetric,
    SystemHealthItem,
)
from app.services.admin_client.dashboard.dashboard_anomalies import detect_dashboard_anomalies
from app.services.admin_client.dashboard.dashboard_tool import get_dashboard_summary


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


def _mock_cc() -> CommandCenterPayload:
    now = datetime.now(timezone.utc)
    return CommandCenterPayload(
        hero_stats=[
            HeroStatItem(label="Total Shipments", value=44, icon="shipments"),
            HeroStatItem(label="Delivered", value=1, icon="delivered"),
            HeroStatItem(label="In Transit", value=13, icon="transit"),
            HeroStatItem(label="Users", value=12, icon="users"),
            HeroStatItem(label="Incidents", value=10, icon="incidents"),
        ],
        today_overview=[
            OverviewMetric(label="Shipments", value="44", trend_percent=0, trend_up=True, icon="s"),
            OverviewMetric(label="Users", value="12", trend_percent=0, trend_up=True, icon="u"),
        ],
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
            ),
        ],
        recent_conversations=[],
        system_health=[
            SystemHealthItem(
                name="FedEx API", key="fedex", status="ok", percent=100, operational=True
            ),
        ],
        user_roles=[],
        pending_invitations=0,
        recent_users=[],
        fedex_metrics=FedexApiMetrics(
            requests_today=0,
            success_rate=0.99,
            latency_ms=100,
            error_rate=0.01,
            requests_series=[],
        ),
        activity_timeline=[],
        open_incidents=10,
        notification_count=0,
        total_users=12,
        online_users=13,
        generated_at=now,
    )


@patch("app.services.admin_client.dashboard.dashboard_tool.build_command_center")
def test_get_dashboard_summary_canonical_fields(mock_cc, db):
    mock_cc.return_value = _mock_cc()
    db.add(
        User(
            email="a@test.com",
            password_hash="x",
            full_name="A",
            role="admin",
            status="active",
            organization_id="o1",
        )
    )
    db.flush()

    summary = get_dashboard_summary(db, lang="fr")
    assert summary["shipments_today"] == 44
    assert summary["delivered_today"] == 1
    assert summary["in_transit"] == 13
    assert summary["active_users"] == 12
    assert summary["total_users"] == 12
    assert summary["open_incidents"] == 10
    assert summary["delayed_shipments"] == 1
    assert "anomalies" in summary
    assert "data_quality" in summary


def test_detect_dashboard_anomalies_active_gt_total():
    data = {
        "lang": "fr",
        "active_users": 14,
        "total_users": 12,
        "online_users": 5,
        "open_incidents": 0,
        "delayed_shipments": 0,
        "blocked_shipments": 0,
        "shipments_today": 0,
        "fedex_requests_today": 0,
        "fedex_error_rate": 0,
        "system_health": [],
        "recent_activity": [],
    }
    flags, quality = detect_dashboard_anomalies(data)
    assert quality["has_inconsistency"] is True
    assert any("Incohérence" in f for f in flags)
