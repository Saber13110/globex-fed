"""Formatage déterministe des réponses dashboard admin."""

from __future__ import annotations

from app.services.admin_client.dashboard.dashboard_compose import compose_dashboard_response
from app.services.admin_client.dashboard.dashboard_types import DashboardTaskType


def format_dashboard_reply(snapshot, plan: DashboardPlan) -> str:
    return compose_dashboard_response(snapshot, plan)


def intent_for_task(task: DashboardTaskType) -> str:
    mapping = {
        DashboardTaskType.platform_overview: "dashboard_overview",
        DashboardTaskType.delayed_shipments: "dashboard_delays",
        DashboardTaskType.quick_delay_report: "dashboard_report",
        DashboardTaskType.recent_activity: "dashboard_activity",
        DashboardTaskType.recent_ai_conversations: "dashboard_conversations",
        DashboardTaskType.recent_audit: "dashboard_audit",
        DashboardTaskType.users_breakdown: "dashboard_users",
        DashboardTaskType.new_users_period: "dashboard_new_users",
    }
    return mapping.get(task, "dashboard_query")
