"""Tests graphiques dashboard admin."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.command_center import (
    CommandCenterPayload,
    FedexApiMetrics,
    HeroStatItem,
    KpiTrendPoint,
    LiveShipmentItem,
)
from app.services.admin_client.dashboard.dashboard_charts import render_dashboard_charts
from app.services.admin_client.dashboard.dashboard_snapshot import DashboardSnapshot


def _snapshot() -> DashboardSnapshot:
    now = datetime.now(timezone.utc)
    cc = CommandCenterPayload(
        hero_stats=[HeroStatItem(label="X", value=1, icon="package")],
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
            requests_today=10,
            success_rate=0.99,
            latency_ms=80,
            error_rate=0.01,
            requests_series=[
                KpiTrendPoint(label="Lun", value=5),
                KpiTrendPoint(label="Mar", value=8),
            ],
        ),
        activity_timeline=[],
        open_incidents=0,
        notification_count=0,
        total_users=3,
        generated_at=now,
    )
    return DashboardSnapshot(
        lang="fr",
        command_center=cc,
        delayed_shipments=cc.live_shipments,
        shipment_status_counts={"delayed": 1},
        users_by_role={"admin": 1, "client": 2},
        activity_level_counts={"INFO": 3, "ERROR": 1},
    )


def test_render_dashboard_charts_non_empty():
    charts = render_dashboard_charts(_snapshot())
    assert charts
    for key, png in charts.items():
        assert len(png) > 100, f"chart {key} empty"
