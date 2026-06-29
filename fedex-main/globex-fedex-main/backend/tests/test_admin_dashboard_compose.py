"""Tests composeur dashboard."""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.command_center import CommandCenterPayload, FedexApiMetrics
from app.services.admin_client.dashboard.dashboard_compose import (
    compose_dashboard_response,
    compose_kpi_list_profile,
    compose_status_profile,
)
from app.services.admin_client.dashboard.dashboard_intent import DashboardPlan, DashboardTaskType
from app.services.admin_client.dashboard.dashboard_reconcile import DashboardQuestionType
from app.services.admin_client.dashboard.dashboard_snapshot import DashboardSnapshot


def _snapshot(summary: dict) -> DashboardSnapshot:
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
        open_incidents=0,
        notification_count=0,
        total_users=10,
        generated_at=now,
    )
    return DashboardSnapshot(lang="fr", command_center=cc, summary=summary)


def test_compose_status_vs_summary_different():
    data = {
        "shipments_today": 44,
        "delivered_today": 1,
        "in_transit": 13,
        "active_users": 12,
        "total_users": 12,
        "open_incidents": 10,
        "delayed_shipments": 2,
        "fedex_requests_today": 0,
        "system_health": [],
        "anomalies": ["10 incident(s) ouvert(s)"],
        "recent_activity": [],
    }
    status = compose_status_profile(data, "fr")
    summary = compose_kpi_list_profile(data, "fr")
    assert "Contrôle santé" in status or "Problème" in status or "Partiel" in status
    assert "KPIs principaux" in summary
    assert status != summary


def test_compose_dashboard_no_duplicate_incidents():
    snap = _snapshot(
        {
            "shipments_today": 44,
            "delivered_today": 1,
            "in_transit": 13,
            "active_users": 12,
            "total_users": 12,
            "online_users": 5,
            "open_incidents": 10,
            "fedex_requests_today": 0,
            "system_health": [],
            "anomalies": [],
            "recent_activity": [],
            "data_quality": {},
        }
    )
    plan = DashboardPlan(
        task_type=DashboardTaskType.platform_overview,
        question_type=DashboardQuestionType.KPI_LIST,
    )
    reply = compose_dashboard_response(snap, plan)
    assert reply.count("Incidents ouverts") <= 1
    assert "Source : Dashboard Admin" in reply
