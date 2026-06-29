"""Tests collecteur dashboard admin."""

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
    ActivityTimelineItem,
    CommandCenterPayload,
    FedexApiMetrics,
    HeroStatItem,
    LiveShipmentItem,
    RecentUserItem,
)
from app.services.admin_client.dashboard.dashboard_snapshot import collect_dashboard_snapshot


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


def _mock_cc(*, delayed: int = 1) -> CommandCenterPayload:
    now = datetime.now(timezone.utc)
    shipments = [
        LiveShipmentItem(
            id=1,
            route="Paris → Lyon",
            origin="Paris",
            destination="Lyon",
            origin_flag="🇫🇷",
            destination_flag="🇫🇷",
            carrier="FedEx",
            tracking_number="817950452196",
            status="Delayed",
            status_key="delayed",
            eta_label="Demain",
            progress_percent=40,
            updated_at=now,
        ),
        LiveShipmentItem(
            id=2,
            route="NY → Paris",
            origin="NY",
            destination="Paris",
            origin_flag="🇺🇸",
            destination_flag="🇫🇷",
            carrier="FedEx",
            tracking_number="817950452197",
            status="In Transit",
            status_key="in_transit",
            eta_label="Lundi",
            progress_percent=70,
            updated_at=now,
        ),
    ]
    if delayed == 0:
        shipments[0] = shipments[0].model_copy(update={"status_key": "in_transit", "status": "In Transit"})

    return CommandCenterPayload(
        hero_stats=[
            HeroStatItem(label="Expéditions", value=12, icon="package"),
            HeroStatItem(label="Livrées", value=8, icon="check"),
        ],
        today_overview=[],
        executive_insights=[],
        kpis=[],
        live_shipments=shipments,
        recent_conversations=[],
        system_health=[],
        user_roles=[],
        pending_invitations=0,
        recent_users=[
            RecentUserItem(
                id=1,
                full_name="Alice",
                email="alice@test.com",
                role="client",
                created_at=now,
            )
        ],
        fedex_metrics=FedexApiMetrics(
            requests_today=42,
            success_rate=0.98,
            latency_ms=120,
            error_rate=0.01,
            requests_series=[],
        ),
        activity_timeline=[
            ActivityTimelineItem(
                time_label="10:00",
                message="Login admin",
                category="auth",
                level="INFO",
                created_at=now,
            ),
            ActivityTimelineItem(
                time_label="10:05",
                message="FedEx timeout",
                category="api",
                level="ERROR",
                created_at=now,
            ),
        ],
        open_incidents=0,
        notification_count=0,
        total_users=5,
        generated_at=now,
    )


@patch("app.services.admin_client.dashboard.dashboard_snapshot.fetch_command_center_and_summary")
def test_collect_dashboard_snapshot_delayed(mock_fetch, db):
    cc = _mock_cc(delayed=1)
    mock_fetch.return_value = (
        cc,
        {
            "delayed_shipments": 1,
            "anomalies": [],
            "data_quality": {"has_inconsistency": False, "inconsistencies": []},
            "lang": "fr",
        },
    )
    db.add(
        User(
            email="u1@test.com",
            password_hash="x",
            full_name="U1",
            role="client",
            status="active",
            organization_id="org-1",
        )
    )
    db.flush()

    snap = collect_dashboard_snapshot(db, lang="fr", period="week")
    assert len(snap.delayed_shipments) == 1
    assert snap.delayed_shipments[0].tracking_number == "817950452196"
    assert snap.delayed_shipments[0].status_key == "delayed"
    assert snap.shipment_status_counts.get("delayed") == 1
    assert snap.activity_level_counts.get("ERROR") == 1
    assert snap.users_by_role.get("client") == 1


@patch("app.services.admin_client.dashboard.dashboard_snapshot.fetch_command_center_and_summary")
def test_collect_dashboard_snapshot_new_users_period(mock_fetch, db):
    cc = _mock_cc()
    mock_fetch.return_value = (
        cc,
        {
            "new_users": [{"full_name": "Alice", "email": "alice@test.com", "role": "client"}],
            "anomalies": [],
            "data_quality": {"has_inconsistency": False, "inconsistencies": []},
            "lang": "en",
        },
    )
    snap = collect_dashboard_snapshot(db, lang="en", period="today")
    assert len(snap.new_users) == 1
    assert snap.new_users[0].email == "alice@test.com"
